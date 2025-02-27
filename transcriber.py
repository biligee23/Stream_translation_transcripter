import threading
import queue
import pyaudio
import json
import tkinter as tk
from tkinter import font
from vosk import Model, KaldiRecognizer
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
import re

# Load Translation Model
MODEL_NAME = "facebook/m2m100_418M"
tokenizer = M2M100Tokenizer.from_pretrained(MODEL_NAME)
model = M2M100ForConditionalGeneration.from_pretrained(MODEL_NAME)

def translate_text(text, src_lang="ja", tgt_lang="en"):
    """Translates Japanese text to English using Marian MT (M2M100)."""
    if not text.strip():
        return ""
    
    try:
        tokenizer.src_lang = src_lang
        tokenized_text = tokenizer(text, return_tensors="pt")
        translated = model.generate(**tokenized_text, forced_bos_token_id=tokenizer.get_lang_id(tgt_lang))
        return tokenizer.decode(translated[0], skip_special_tokens=True)
    except Exception as e:
        print(f"Translation Error: {e}")
        return ""

def split_into_sentences(text):
    """Splits text into sentences using Japanese punctuation."""
    sentences = re.split(r'[。！？]', text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]

class TranscriptionOverlay:
    """Tkinter UI for displaying real-time translated transcription."""
    def __init__(self, text_queue):
        self.root = tk.Tk()
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.configure(bg="black")

        # Screen & Window Config
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = 800
        window_height = 150
        x_position = (screen_width - window_width) // 2
        y_position = screen_height - window_height - 100
        self.root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")

        # Transparency
        self.root.attributes("-transparentcolor", "black")

        # Fonts
        subtitle_font = font.Font(family="Arial", size=24, weight="bold")

        # Shadow Label for Contrast
        self.label_shadow = tk.Label(
            self.root, text="", font=subtitle_font, fg="black", bg="black", wraplength=780, justify="center"
        )
        self.label_shadow.place(relx=0.5, rely=0.5, anchor="center", x=2, y=2)

        # Main Text Label
        self.label = tk.Label(
            self.root, text="", font=subtitle_font, fg="white", bg="black", wraplength=780, justify="center"
        )
        self.label.place(relx=0.5, rely=0.5, anchor="center")

        self.text_queue = text_queue  # Queue for UI updates
        self.root.after(100, self.update_overlay)  # Update loop

    def update_overlay(self):
        """Updates UI with translated text from queue."""
        try:
            while not self.text_queue.empty():
                text = self.text_queue.get_nowait()
                self.label.config(text=text)
                self.label_shadow.config(text=text)
        except queue.Empty:
            pass
        self.root.after(100, self.update_overlay)

    def start(self):
        """Starts the Tkinter UI."""
        self.root.mainloop()

def audio_transcription(text_queue):
    """Handles real-time speech recognition & translation."""
    MODEL_PATH = "./models/vosk-model-ja-0.22"
    model = Model(MODEL_PATH)
    rec = KaldiRecognizer(model, 16000)

    audio = pyaudio.PyAudio()
    stream = audio.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=16000)

    print("Listening... Press Ctrl+C to stop.")

    partial_buffer = ""

    try:
        while True:
            audio_data = stream.read(16000, exception_on_overflow=False)

            if rec.PartialResult():
                partial_result = json.loads(rec.PartialResult())
                transcription = partial_result.get('partial', '')

                if transcription:
                    partial_buffer += transcription

                # If a full sentence is formed, translate
                if len(partial_buffer) > 10 and any(punct in partial_buffer for punct in "。！？"):
                    sentences = split_into_sentences(partial_buffer)
                    for sentence in sentences:
                        translated_text = translate_text(sentence)
                        if translated_text.strip():
                            text_queue.put(translated_text)
                    partial_buffer = ""

            if rec.AcceptWaveform(audio_data):
                result = json.loads(rec.Result())
                transcription = result.get('text', '')

                if transcription:
                    sentences = split_into_sentences(transcription)
                    for sentence in sentences:
                        translated_text = translate_text(sentence)
                        if translated_text.strip():
                            text_queue.put(translated_text)

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()

if __name__ == "__main__":
    text_queue = queue.Queue()

    # Start speech recognition in a background thread
    transcription_thread = threading.Thread(target=audio_transcription, args=(text_queue,), daemon=True)
    transcription_thread.start()

    # Start the Tkinter UI in the main thread
    overlay = TranscriptionOverlay(text_queue)
    overlay.start()
