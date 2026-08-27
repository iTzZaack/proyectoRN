"""
wake_word.py
Detección ligera y 100% OFFLINE de la palabra de activación ("wake word") 
usando Vosk de forma local sin depender de servidores de Google ni internet.
"""
import os
import re
import time
import json
import sounddevice as sd
from vosk import Model, KaldiRecognizer
from config import WAKE_WORD

_vosk_model = None

_KRY_VARIANTS = ["oye kry", "oye kray", "oye cray", "oye krai", "oye crei", "oye cri"]


def _get_model():
    global _vosk_model
    if _vosk_model is None:
        model_path = "models/vosk/vosk-model-small-es-0.42"
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"No se encontró el modelo Vosk en: {model_path}")
        _vosk_model = Model(model_path)
    return _vosk_model


def _normalize(text: str) -> str:
    return text.lower().strip()


def _matches_wake_word(text: str) -> bool:
    text = _normalize(text)
    candidates = [WAKE_WORD] if WAKE_WORD != "oye kry" else _KRY_VARIANTS
    for word in candidates:
        if re.search(rf"\b{re.escape(word)}\b", text):
            return True
    return False


def listen_for_wake_word(stop_event, on_detected, on_status=None, pause_event=None):
    """
    Escucha continuamente el micrófono de forma OFFLINE procesando
    audio en bloques mediante Vosk local.
    """
    try:
        model = _get_model()
        samplerate = 16000
        rec = KaldiRecognizer(model, samplerate)

        # Usar sounddevice para capturar audio local en bloques
        with sd.RawInputStream(samplerate=samplerate, blocksize=4000, dtype='int16',
                               channels=1) as stream:
            while not stop_event.is_set():
                if pause_event is not None and pause_event.is_set():
                    time.sleep(0.2)
                    continue

                data, overflowed = stream.read(2000)
                if rec.AcceptWaveform(bytes(data)):
                    res = json.loads(rec.Result())
                    text = res.get("text", "")
                    
                    if text:
                        if on_status:
                            on_status(f'Escuché: "{text}" (esperando "{WAKE_WORD}")')
                            
                        if _matches_wake_word(text):
                            if on_status:
                                on_status("¡Palabra clave detectada!")
                            # Ejecución síncrona bloqueante tal como requería la lógica original
                            on_detected()
                            rec.Reset()

    except Exception as exc:
        if on_status:
            on_status(f"Error en escucha offline: {exc}")
        time.sleep(1)