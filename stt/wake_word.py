"""
wake_word.py
Detección ligera de palabra de activación ("wake word") usando
SpeechRecognition (motor gratuito de Google, requiere internet
pero no requiere API key).

No usa Whisper aquí porque Whisper no está pensado para escuchar
continuamente en tiempo real; este módulo solo detecta CUÁNDO
alguien dijo la palabra clave. Una vez detectada, el comando real
se re-graba y se transcribe con Whisper (stt/whisper_stt.py) para
mayor precisión.
"""
import re
import time
import speech_recognition as sr
from config import WAKE_WORD

# Variantes fonéticas comunes con las que el reconocedor en español puede
# transcribir "Oye Kry" (se escribe k-r-y, pero se pronuncia "Kray") por
# acento o mala pronunciación. Se comparan como PALABRA COMPLETA, no como
# substring, para evitar falsos positivos con palabras que solo contienen
# estas letras por casualidad.
_KRY_VARIANTS = ["oye kry", "oye kray", "oye cray", "oye krai", "oye crei"]


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
    Escucha continuamente el micrófono en un hilo bloqueante hasta
    detectar la palabra de activación (WAKE_WORD) o hasta que
    stop_event esté activado.

    on_detected: callback SIN ARGUMENTOS que se llama al detectar la
    palabra. IMPORTANTE: debe ejecutarse de forma síncrona/bloqueante
    (no lanzar un hilo nuevo y devolver de inmediato), porque mientras
    on_detected no retorne, este bucle NO vuelve a abrir el micrófono.
    Si on_detected devolviera control enseguida y otra parte de la app
    abriera el micrófono en paralelo (por ejemplo para grabar el
    comando), dos aperturas simultáneas del mismo dispositivo de audio
    pueden crashear PyAudio en Windows.

    pause_event: threading.Event opcional. Mientras esté activado, este
    bucle NO intenta abrir el micrófono (se usa para pausar la escucha
    de wake word durante comandos manuales, por la misma razón de
    arriba).

    on_status: callback opcional para reportar mensajes de estado/errores.
    """
    recognizer = sr.Recognizer()
    mic = sr.Microphone()

    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)

    while not stop_event.is_set():
        if pause_event is not None and pause_event.is_set():
            time.sleep(0.2)
            continue
        try:
            with mic as source:
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=4)
            text = recognizer.recognize_google(audio, language="es-ES")
            if on_status:
                on_status(f'Escuché: "{text}" (esperando "{WAKE_WORD}")')
            if _matches_wake_word(text):
                on_detected()
        except sr.WaitTimeoutError:
            continue  # nadie habló en ese intervalo, seguir escuchando
        except sr.UnknownValueError:
            continue  # audio no reconocible, seguir escuchando
        except sr.RequestError as exc:
            if on_status:
                on_status(f"Sin conexión para detectar la palabra de activación: {exc}")
            continue
        except Exception as exc:
            if on_status:
                on_status(f"Error en la escucha de wake word: {exc}")
            continue
