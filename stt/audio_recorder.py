"""
audio_recorder.py
Graba el comando de voz del usuario hasta que detecta que dejó de
hablar (silencio), en vez de una duración fija. Usa SpeechRecognition
solo como "oído" para saber cuándo cortar la grabación — la
transcripción real la sigue haciendo Whisper (whisper_stt.py), no este
módulo.
"""
import speech_recognition as sr
from config import COMMAND_MAX_SECONDS, SILENCE_SECONDS


def record_command(output_path: str, listen_timeout: float = 8) -> str | None:
    """
    Escucha el micrófono y graba desde que detecta voz hasta que
    detecta 'SILENCE_SECONDS' segundos de silencio (o hasta
    COMMAND_MAX_SECONDS como tope de seguridad). Guarda el resultado
    como .wav en output_path y devuelve la ruta.

    listen_timeout: cuántos segundos espera a que Zaack EMPIECE a
    hablar antes de rendirse. Si nadie habla en ese tiempo, devuelve
    None en vez de lanzar una excepción — esto es clave para el modo
    de conversación continua (ui/desktop_app.py), donde "nadie habló"
    significa simplemente "se acabó la conversación", no un error.
    """
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = SILENCE_SECONDS  # segundos de silencio para cortar
    mic = sr.Microphone()

    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(source, timeout=listen_timeout, phrase_time_limit=COMMAND_MAX_SECONDS)
        except sr.WaitTimeoutError:
            return None

    with open(output_path, "wb") as f:
        f.write(audio.get_wav_data())

    return output_path
