"""
whisper_stt.py
Convierte audio a texto usando Whisper local (openai-whisper).
No requiere API key: el modelo corre en la máquina del usuario.
"""
import whisper
from config import WHISPER_MODEL_SIZE

_model = None


def _get_model():
    """Carga el modelo una sola vez (perezoso) para no recargarlo en cada llamada."""
    global _model
    if _model is None:
        print(f"[whisper_stt] Cargando modelo Whisper '{WHISPER_MODEL_SIZE}'...")
        _model = whisper.load_model(WHISPER_MODEL_SIZE)
    return _model


def transcribe_audio(audio_path: str, language: str = "es") -> str:
    """
    Transcribe un archivo de audio (wav/mp3) a texto.
    Devuelve cadena vacía si no se reconoce nada, en vez de lanzar excepción.
    """
    try:
        model = _get_model()
        result = model.transcribe(
            audio_path,
            language=language,
            fp16=False,
            # Evita que Whisper "invente" texto repetido en tramos de
            # silencio o ruido (alucinación típica de Whisper), y evita
            # que un error de transcripción en una frase arrastre errores
            # a las frases siguientes dentro del mismo audio.
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
        )
        return result.get("text", "").strip()
    except Exception as exc:
        print(f"[ERROR whisper_stt] {exc}")
        return ""
