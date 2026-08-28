import subprocess
import wave
import os
import traceback

class PiperTTS:
    def __init__(self, model_path="models/piper/es_ES-davefx-medium.onnx"):
        self.model_path = model_path

    def generate_audio_file(self, text: str, output_path: str = "output.wav") -> str | None:
        if not text or not text.strip():
            return None
        
        try:
            cmd = ["piper", "--model", self.model_path, "--output-raw"]
            proc = subprocess.Popen(
                cmd, 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.DEVNULL
            )
            raw_audio, _ = proc.communicate(input=text.encode('utf-8'))

            if not raw_audio:
                return None

            with wave.open(output_path, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(22050)
                wav_file.writeframes(raw_audio)

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
            return None

        except Exception as exc:
            print(f"[ERROR PiperTTS] {exc}")
            traceback.print_exc()
            return None

_piper_instance = None

def text_to_speech(text: str, output_path: str = "output.wav", voice: str = None) -> str | None:
    global _piper_instance
    if _piper_instance is None:
        _piper_instance = PiperTTS()
    return _piper_instance.generate_audio_file(text, output_path)