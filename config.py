"""
config.py
Carga la configuración del proyecto desde variables de entorno (.env).
Nunca poner credenciales directamente en el código.
"""
import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Modelos disponibles para cambiar en caliente ("usa phi3", "cambia a
# llama") y para comparar respuestas ("compara los modelos: <pregunta>").
# Deben estar descargados en Ollama (`ollama pull <modelo>`).
AVAILABLE_MODELS = [
    m.strip() for m in os.getenv("AVAILABLE_MODELS", "phi3:mini,llama3.1:8b").split(",") if m.strip()
]
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")  # tiny, base, small, medium
# "small" reconoce notablemente mejor el español hablado rápido/informal que
# "base", y sigue corriendo sin GPU dedicada (un poco más lento al cargar,
# no en cada transcripción). Si tu máquina es muy limitada, volvé a "base".
TTS_VOICE = os.getenv("TTS_VOICE", "es-ES-ElviraNeural")  # voz femenina en español
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "10"))

# Palabra (o frase corta) de activación. En minúsculas y sin tildes para
# que la comparación sea más tolerante. Por defecto "oye kry" (se
# pronuncia "oye Kray", ver stt/wake_word.py para las variantes
# fonéticas toleradas).
WAKE_WORD = os.getenv("WAKE_WORD", "oye kry").lower()

# Grabación del comando: dura hasta que detecta SILENCE_SECONDS de
# silencio, con COMMAND_MAX_SECONDS como tope de seguridad para que
# nunca se quede grabando indefinidamente.
SILENCE_SECONDS = float(os.getenv("SILENCE_SECONDS", "1.5"))
COMMAND_MAX_SECONDS = int(os.getenv("COMMAND_MAX_SECONDS", "20"))

# Modo de conversación continua: después de que Kry responde, sigue
# escuchando SIN pedir de nuevo la wake word ("Oye Kry...") mientras
# Zaack siga hablando. CONVERSATION_WINDOW_SECONDS es la ventana total
# (se renueva cada vez que Zaack dice algo, como un "sigo despierto
# mientras haya charla"). CONVERSATION_TURN_TIMEOUT es cuánto espera,
# en cada turno individual, a que Zaack EMPIECE a hablar antes de
# asumir que la conversación terminó y volver a pedir "Oye Kry...".
CONVERSATION_WINDOW_SECONDS = int(os.getenv("CONVERSATION_WINDOW_SECONDS", "180"))
CONVERSATION_TURN_TIMEOUT = float(os.getenv("CONVERSATION_TURN_TIMEOUT", "8"))
