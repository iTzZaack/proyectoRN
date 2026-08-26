"""
sounds.py
Genera dos tonos cortos ("beeps") por código, sin depender de ningún
archivo de audio externo, para que Zaack sepa en qué momento el
micrófono está capturando su voz:

- Tono agudo y corto ("tin"): Kry EMPEZÓ a escuchar un comando.
- Tono grave: Kry dejó de escuchar (volvió a esperar la wake word).

Se generan una sola vez con numpy (ya es dependencia del proyecto) y
se cachean como .wav en la carpeta temporal del sistema, para no
tener que regenerarlos en cada turno de la conversación.
"""
import os
import tempfile
import wave

import numpy as np

_SAMPLE_RATE = 44100


def _generate_tone(freq: float, duration_ms: int, volume: float = 0.35) -> str:
    path = os.path.join(tempfile.gettempdir(), f"kry_tone_{int(freq)}_{duration_ms}.wav")
    if os.path.exists(path):
        return path

    n_samples = int(_SAMPLE_RATE * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, n_samples, endpoint=False)
    tone = np.sin(freq * t * 2 * np.pi)

    # Fade in/out muy corto para que no truene al empezar o cortarse feo.
    fade_len = max(1, int(_SAMPLE_RATE * 0.01))
    envelope = np.ones(n_samples)
    envelope[:fade_len] = np.linspace(0, 1, fade_len)
    envelope[-fade_len:] = np.linspace(1, 0, fade_len)

    audio = np.int16(tone * envelope * volume * 32767)

    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(_SAMPLE_RATE)
        f.writeframes(audio.tobytes())

    return path


_listen_tone_path = None
_idle_tone_path = None


def get_listen_tone_path() -> str:
    """Tono corto y agudo: 'ya te estoy escuchando'."""
    global _listen_tone_path
    if _listen_tone_path is None:
        _listen_tone_path = _generate_tone(freq=880, duration_ms=120)
    return _listen_tone_path


def get_idle_tone_path() -> str:
    """Tono más grave y un poco más largo: 'dejé de escuchar, decime Kry de nuevo'."""
    global _idle_tone_path
    if _idle_tone_path is None:
        _idle_tone_path = _generate_tone(freq=330, duration_ms=180)
    return _idle_tone_path
