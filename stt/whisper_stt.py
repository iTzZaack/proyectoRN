import wave
import json
from vosk import Model, KaldiRecognizer

_vosk_model = None

def _get_model():
    global _vosk_model
    if _vosk_model is None:
        _vosk_model = Model("models/vosk/vosk-model-small-es-0.42")
    return _vosk_model

def transcribe_audio(audio_path: str, language: str = "es") -> str:
    """
    Transcribe un archivo de audio (WAV) a texto usando Vosk local.
    Devuelve cadena vacía si no se reconoce nada o hay error.
    """
    try:
        model = _get_model()
        
        wf = wave.open(audio_path, "rb")
        rec = KaldiRecognizer(model, wf.getframerate())
        rec.SetWords(True)

        results = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                if res.get("text"):
                    results.append(res["text"])

        final_res = json.loads(rec.FinalResult())
        if final_res.get("text"):
            results.append(final_res["text"])

        wf.close()
        return " ".join(results).strip()
    except Exception as exc:
        print(f"[ERROR vosk_stt] {exc}")
        return ""