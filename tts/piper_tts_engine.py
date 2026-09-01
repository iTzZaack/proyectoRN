import subprocess
import os
import traceback
import tempfile
import uuid
import unicodedata

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ruta al modelo .onnx existente
DEFAULT_MODEL_PATH = os.path.join(BASE_DIR, "models", "piper", "es_ES-davefx-medium.onnx")

class PiperTTS:
    def __init__(self, model_path=None):
        self.model_path = model_path or DEFAULT_MODEL_PATH

    def generate_audio_file(self, text: str, output_path: str = None) -> str | None:
        if not text or not text.strip():
            return None

        # Normaliza el texto: junta las tildes/acentos separados con su
        # vocal en un solo carácter (á, é, í, ...). Sin esto, Piper a
        # veces "lee" la tilde por separado en vez de aplicarla a la
        # vocal, sobre todo con texto que pasó por varias transformaciones
        # de string (como la respuesta del LLM).
        text = unicodedata.normalize("NFC", text)

        if not output_path:
            output_path = os.path.join(tempfile.gettempdir(), f"piper_{uuid.uuid4().hex}.wav")

        if not os.path.exists(self.model_path):
            print(f"[ERROR PiperTTS] No existe el modelo .onnx en: {self.model_path}")
            return None

        # Archivo temporal para evitar bloqueos de stdin en Windows
        temp_txt = os.path.join(tempfile.gettempdir(), f"piper_in_{uuid.uuid4().hex}.txt")

        try:
            with open(temp_txt, "w", encoding="utf-8") as f:
                f.write(text)

            # Ejecuta el módulo instalado en el entorno de Python mediante "python -m piper"
            cmd = f'python -m piper --model "{self.model_path}" --output_file "{output_path}" < "{temp_txt}"'
            
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8"
            )

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path

            print(f"[ERROR PiperTTS] Stderr: {result.stderr}")
            return None

        except Exception as exc:
            print(f"[ERROR PiperTTS Exception] {exc}")
            traceback.print_exc()
            return None
            
        finally:
            if os.path.exists(temp_txt):
                try:
                    os.remove(temp_txt)
                except Exception:
                    pass

_piper_instance = None

def text_to_speech(text: str, output_path: str = None, voice: str = None) -> str | None:
    global _piper_instance
    if _piper_instance is None:
        _piper_instance = PiperTTS()
    return _piper_instance.generate_audio_file(text, output_path)