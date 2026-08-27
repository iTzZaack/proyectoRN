# Mini-JARVIS — Kry

Asistente de voz conversacional basado en un LLM local (Ollama), con pipeline
STT → LLM → TTS **100% local (offline-first)**, memoria conversacional,
interfaz de escritorio con avatar animado y un módulo de exploración de la
arquitectura Transformer (tokenización, embeddings y self-attention).

El núcleo del sistema (reconocimiento de voz, detección de la palabra de
activación y síntesis de voz) funciona sin conexión a internet. Un conjunto
de funciones opcionales (YouTube, Google, páginas web) requiere internet y
se activa automáticamente cuando hay red disponible, sin afectar el resto
del asistente cuando no la hay.

> ⚠️ **Este proyecto requiere Windows.** La apertura de aplicaciones
> instaladas, la automatización de la Calculadora (`pywinauto`) y varias
> funciones del sistema dependen de APIs exclusivas de Windows (accesos
> directos del Menú Inicio, `os.startfile`, comandos `start`). La app web
> (Streamlit, `app.py`) es la única parte que podría probarse en otro
> sistema operativo, pero sin esas funciones extra.

## Requisitos previos

- **Windows 10/11** (ver aviso arriba).
- Python 3.11 (recomendado; algunas dependencias como `torch` no siempre
  tienen soporte inmediato para versiones de Python muy nuevas). Agregado
  al PATH (`python --version` debe funcionar desde cualquier carpeta).
- [Ollama](https://ollama.com) instalado y corriendo localmente.
- [Git para Windows](https://git-scm.com/install/windows) instalado.
- ffmpeg instalado en el sistema (requerido por Whisper). En Windows, la
  forma más simple es con winget desde PowerShell:
  ```powershell
  winget install --id gyan.ffmpeg --accept-source-agreements --accept-package-agreements
  ```
  Después de instalarlo, cierra y vuelve a abrir la terminal para que
  reconozca el comando `ffmpeg`.
- Un micrófono y parlantes/audífonos funcionando (para la activación por
  voz y las respuestas habladas).

## Instalación

```powershell
# 1. Clonar el repositorio
git clone <url-del-repo>
cd mini-jarvis

# 2. Crear entorno virtual (con Python 3.11)
py -3.11 -m venv venv

# 3. Activar el entorno virtual (PowerShell)
.\venv\Scripts\Activate.ps1
```

Si el paso 3 falla con un error de **"la ejecución de scripts está
deshabilitada en este sistema"**, es la política de ejecución de
PowerShell bloqueando el script de activación (no un problema del
proyecto). Se soluciona una sola vez por usuario:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
Confirma con "S" y vuelve a correr `.\venv\Scripts\Activate.ps1`. Si en
cambio usas CMD en vez de PowerShell, el comando de activación es
`venv\Scripts\activate.bat`.

Con el entorno ya activado (aparece `(venv)` al inicio de la línea):

```powershell
# 4. Instalar dependencias
pip install -r requirements.txt
```

**Si `pip install` falla específicamente en `PyAudio`**, es un problema
conocido de Windows (PyAudio necesita compilar contra PortAudio y suele
faltar el compilador de C++). Solución:
```powershell
pip install pipwin
pipwin install pyaudio
pip install -r requirements.txt   # vuelve a correr para instalar el resto
```

```powershell
# 5. Configurar variables de entorno
copy .env.example .env
# Ajusta OLLAMA_MODEL, WAKE_WORD, etc. si hace falta
```

```powershell
# 6. Descargar AMBOS modelos LLM en Ollama
# Se descargan los dos porque el proyecto permite cambiar de modelo en
# caliente y comparar sus respuestas (ver "Selección y comparación de
# modelos" más abajo) — con solo uno descargado, esas dos funciones fallan.
ollama pull phi3:mini
ollama pull llama3.1:8b
ollama serve   # dejar corriendo en una terminal aparte
```

```powershell
# 7. Verificar que los modelos de Vosk (wake word) y Piper (TTS) están
# presentes — vienen incluidos en el repositorio, no hace falta
# descargarlos aparte. Esto es justo lo que permite que el proyecto
# corra en el laboratorio sin conexión a internet.
Get-ChildItem -Recurse models
```

Si por algún motivo la carpeta `models/` llegara vacía (por ejemplo al
clonar una copia distinta del repo donde no se incluyeron), se pueden
regenerar así, con conexión a internet:

```powershell
# Modelo de wake word (Vosk)
python -c "from vosk import Model; Model(lang='es')"
python -c "import os, shutil; src = os.path.expanduser('~/.cache/vosk/vosk-model-small-es-0.42'); dst = 'models/vosk/vosk-model-small-es-0.42'; shutil.move(src, dst) if os.path.exists(src) else None"

# Modelo de voz (Piper)
python -c "import urllib.request, os; os.makedirs('models/piper', exist_ok=True); urllib.request.urlretrieve('https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx', 'models/piper/es_ES-davefx-medium.onnx'); urllib.request.urlretrieve('https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json', 'models/piper/es_ES-davefx-medium.onnx.json')"
```

Los modelos de Vosk (~57MB) y Piper (~60MB) SÍ se incluyen en este
repositorio (a diferencia de un enfoque más común donde se excluyen por
tamaño), precisamente para que el proyecto se pueda instalar y ejecutar
en máquinas sin conexión a internet, como las del laboratorio del
instituto.

La primera vez que se ejecute la app, Whisper también descargará su
modelo (`small`, unos cientos de MB) automáticamente — asegúrate de tener
conexión a internet la primera vez.

### Prueba rápida de Vosk y Piper (opcional)

Para confirmar que el micrófono y los parlantes funcionan bien con estos
modelos antes de correr la app completa:

```powershell
# Prueba rápida de voz (TTS con Piper)
python -c "import subprocess, sounddevice as sd, numpy as np; cmd = ['piper', '--model', 'models/piper/es_ES-davefx-medium.onnx', '--output-raw']; proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL); raw, _ = proc.communicate(input='Probando la voz local del proyecto'.encode('utf-8')); sd.play(np.frombuffer(raw, dtype=np.int16), samplerate=22050); sd.wait()"

# Prueba rápida de micrófono (STT con Vosk, escucha 10 segundos)
python -c "import sounddevice as sd, queue, json, time, vosk; model = vosk.Model('models/vosk/vosk-model-small-es-0.42'); rec = vosk.KaldiRecognizer(model, 16000); q = queue.Queue(); print('Habla ahora (10 seg)...'); stream = sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16', channels=1, callback=lambda ind, f, t, s: q.put(bytes(ind))); stream.start(); start = time.time(); [print('Escuchado:', json.loads(rec.Result()).get('text', '')) if rec.AcceptWaveform(q.get()) else None for _ in iter(lambda: time.time() - start < 10, False)]; stream.stop()"
```

### Elección del modelo LLM

Por defecto el proyecto usa `phi3:mini` (~3.8B parámetros) porque el
requisito del proyecto exige que se pueda ejecutar "en una máquina distinta
a la del equipo", incluyendo equipos con recursos limitados (como los del
instituto). Este modelo corre razonablemente bien incluso sin GPU dedicada.
`llama3.1:8b` queda disponible para comparar o cambiar a mejor calidad de
respuesta en máquinas más potentes, cambiando `OLLAMA_MODEL` en tu copia
local de `.env` (nunca en `.env.example`):

```
OLLAMA_MODEL=llama3.1:8b
```

## Ejecución

### Opción 1: Interfaz web (Streamlit) — requiere clic para hablar

```bash
streamlit run app.py
```

Abre el navegador en `http://localhost:8501`, graba tu voz y espera la
respuesta hablada de Kry.

### Opción 2: App de escritorio con activación por voz ("Oye Kry...")

```bash
python -m ui.desktop_app
```

Esta versión permite decir "Oye Kry..." para activarla, sin necesidad de
hacer clic (requisito opcional 5.2, palabra de activación). También
tiene un botón manual como respaldo si el reconocimiento de la palabra
de activación falla.

Además de hablarle, se le puede escribir directamente en el campo de
texto de abajo (tecla Enter o botón "Enviar"): pasa por exactamente la
misma lógica (funciones del sistema, comparación de modelos, LLM) y
Kry responde igual, hablado y animando su avatar, sin importar si el
pedido llegó por voz o por texto.

Notas sobre el wake word:
- La palabra de activación se configura en `.env` con `WAKE_WORD` (por
  defecto "oye kry").
- La detección de la palabra de activación usa **Vosk**, un motor de
  reconocimiento de voz 100% local — no requiere internet en ningún
  momento. El comando real que sigue a la palabra de activación se
  transcribe con Whisper localmente para mayor precisión.

### Funciones del sistema (valor agregado, requisito opcional 5.2)

Kry reconoce estos comandos directos sin pasar por el LLM
(`utils/system_functions.py`). La mayoría son 100% locales; dos de ellas
(YouTube y Google) requieren conexión a internet y se activan solo si hay
red disponible:

**Funciones 100% locales (sin internet):**
- **Hora y fecha**: "¿Qué hora es?", "¿Qué fecha es?"
- **Abrir cualquier aplicación instalada**: "Abre Word", "Abre Minecraft",
  "Abre la calculadora". No es una lista fija: se arma un índice
  automático leyendo los accesos directos del Menú Inicio de Windows, así
  que cubre lo que sea que tengas instalado. Si el nombre es ambiguo (ej.
  hay más de un launcher de Minecraft instalado), Kry pregunta cuál
  antes de abrir nada.
- **Calculadora real**: "Cuánto es 2 más 2", "resuelve 100 entre 4",
  "abre la calculadora y haz 15 por 4". Kry calcula el resultado y
  además abre la Calculadora de Windows y escribe la operación ahí mismo
  usando automatización de interfaz (`pywinauto`), no solo lo dice de
  palabra.
- **Temporizador**: "Temporizador de 5 minutos".

**Funciones que requieren internet (se activan si hay conexión):**
- **YouTube**: "Pon [canción] en YouTube", "busca [canción] en YouTube",
  "entra a YouTube y busca [canción]" — cualquier orden en que se
  mencione "YouTube" abre DIRECTO el video real (usa `yt-dlp` para
  resolver el primer resultado), no solo la página de búsqueda.
- **Google**: "Busca [algo] en Google", "googlea [algo]", "entra a Google
  y busca [algo]".
- **Abrir cualquier página web**: "Entra a Netflix", "ve a Wikipedia",
  "abre la página de Mercado Libre", o directamente un dominio.
- **Buscar en internet (genérico)**: "Busca [algo] en internet".

Todos estos patrones toleran que el pedido venga en subjuntivo ("quiero
que abras...", "...y busques...") y con o sin tildes, no solo en la
forma imperativa exacta ("abre", "busca").

### Selección y comparación de modelos LLM (valor agregado)

`llm/model_commands.py` agrega dos comandos más, usando los modelos
listados en `AVAILABLE_MODELS` (por defecto `phi3:mini` y `llama3.1:8b`,
configurable en `.env`):

- **Cambiar de modelo en caliente**, sin perder la memoria de la
  conversación: "Usa phi3", "Cambia al modelo llama".
- **Comparar respuestas entre modelos** con la misma pregunta, sin tocar
  la memoria principal: "Compara los modelos: ¿qué es un transformer?".
  Es una buena demo en vivo para la sustentación (sección 12 del PDF),
  para mostrar cómo responde distinto un modelo chico vs uno más grande.

Ambos modelos deben estar descargados en Ollama (ver paso 6 de la
instalación).

### Conversación continua y aviso sonoro de escucha (valor agregado)

En la app de escritorio (`ui/desktop_app.py`), después de que Kry
responde, se queda escuchando el siguiente turno SIN que tengas que
decir "Oye Kry..." de nuevo solo si su respuesta fue una pregunta real
(necesita más información tuya para completar el pedido). Si el pedido
ya se cumplió, vuelve a esperar la palabra de activación.

Además, un tono corto y agudo suena cada vez que el micrófono EMPIEZA a
grabar tu comando, y un tono más grave suena cuando Kry vuelve al modo
de espera. Los tonos se generan por código (`utils/sounds.py`), sin
archivos de audio externos.

### Botón de cancelar

El botón "⏹ Detener / Cancelar" corta la generación del LLM a mitad de
camino y detiene el audio que esté sonando, igual que el botón de stop
de ChatGPT o Gemini.

## Módulo de exploración teórica

```bash
python -m exploration.attention_explorer
```

Esto imprime la tokenización, la forma de los embeddings y guarda una
imagen `attention.png` con el mapa de self-attention de una frase de ejemplo.
Puedes editar el texto de entrada en el bloque `if __name__ == "__main__":`
al final del archivo, o importar `explore_text()` desde otro script/notebook.

## Estructura del proyecto

```
mini-jarvis/
├── app.py                       # UI web + orquestador (Streamlit, requiere clic)
├── ui/desktop_app.py            # UI de escritorio con activación por voz ("Oye Kry...")
├── config.py                    # Variables de entorno
├── stt/whisper_stt.py           # Voz -> texto (Whisper local)
├── stt/wake_word.py             # Detección de la palabra de activación (Vosk, local)
├── stt/audio_recorder.py        # Grabación del comando tras la palabra de activación
├── llm/ollama_client.py         # Cliente LLM + memoria conversacional
├── llm/model_commands.py        # Cambio y comparación de modelos en caliente
├── llm/system_prompt.py         # Personalidad de Kry
├── tts/                         # Texto -> voz (Piper, local)
├── utils/system_functions.py    # Funciones del sistema (apps, calculadora, temporizador, YouTube, Google)
├── exploration/attention_explorer.py  # Tokenización/embeddings/atención
├── models/vosk/                 # Modelo de wake word (incluido en el repo, ~57MB)
├── models/piper/                # Modelo de voz TTS (incluido en el repo, ~60MB)
└── utils/logger.py
```

## Limitaciones conocidas

- El modelo LLM local puede generar respuestas incorrectas o alucinar datos.
- Las funciones de búsqueda web (YouTube, Google) no están disponibles sin
  conexión a internet; el resto del asistente sigue funcionando con
  normalidad.
- La calidad de la transcripción depende del tamaño del modelo Whisper
  elegido y de la calidad del micrófono.

## Modelos y proveedores usados

- LLM: Ollama (modelo configurable en `.env`, por defecto `phi3:mini`)
- STT (comando): OpenAI Whisper (ejecución local)
- Wake word: Vosk (`vosk-model-small-es-0.42`), 100% local
- TTS: Piper (`es_ES-davefx-medium`), motor neuronal 100% local
- Exploración de arquitectura: `dccuchile/bert-base-spanish-wwm-uncased` vía Hugging Face Transformers