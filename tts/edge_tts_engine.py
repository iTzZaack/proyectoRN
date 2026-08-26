"""
edge_tts_engine.py
Convierte texto a voz usando edge-tts (gratuito, requiere internet
solo para llamar al servicio de Microsoft Edge, pero sin API key).

Si se necesita 100% offline, se puede sustituir por pyttsx3.
"""
import asyncio
import traceback
import edge_tts
from config import TTS_VOICE


async def _synthesize(text: str, output_path: str, voice: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def text_to_speech(text: str, output_path: str = "output.mp3", voice: str = TTS_VOICE) -> str | None:
    """
    Genera un archivo de audio a partir de texto.
    Devuelve la ruta del archivo o None si falla.
    """
    if not text or not text.strip():
        return None
    try:
        asyncio.run(_synthesize(text, output_path, voice))
        return output_path
    except Exception as exc:
        print(f"[ERROR edge_tts_engine] {exc}")
        traceback.print_exc()
        return None
