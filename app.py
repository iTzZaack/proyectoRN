"""
app.py
Interfaz y orquestador de Kry (Streamlit).
Coordina el flujo: audio -> STT -> LLM -> TTS -> reproducción,
y muestra el estado del sistema (escuchando / pensando / respondiendo / error).
"""
import streamlit as st
import tempfile
import os

from stt.whisper_stt import transcribe_audio
from tts.edge_tts_engine import text_to_speech
from llm.ollama_client import OllamaChatClient
from utils.logger import log
from utils.system_functions import try_handle_system_function, resolve_pending_app_choice
from llm.model_commands import try_handle_model_command

st.set_page_config(page_title="Kry", page_icon="✨")
st.title("✨ Kry")
st.caption("Asistente de voz basado en un LLM local (Ollama) — proyecto integrador.")

# --- Estado de sesión ---
if "chat_client" not in st.session_state:
    st.session_state.chat_client = OllamaChatClient()
if "messages" not in st.session_state:
    st.session_state.messages = []  # para mostrar en pantalla (no es la memoria interna del LLM)
if "status" not in st.session_state:
    st.session_state.status = "En espera"
if "pending_app_choice" not in st.session_state:
    # Cuando "abrir X" es ambiguo (ej. varios "Minecraft" instalados),
    # acá se guardan las opciones {nombre: ruta} hasta que el usuario
    # aclare cuál quiere en su próximo turno.
    st.session_state.pending_app_choice = None

status_placeholder = st.empty()


def set_status(text: str):
    st.session_state.status = text
    status_placeholder.info(f"Estado: {text}")


set_status(st.session_state.status)

# --- Entrada de audio ---
st.subheader("Habla con Kry")
audio_value = st.audio_input("Graba tu mensaje")

if audio_value is not None:
    # 1. ESCUCHANDO -> guardar audio temporal
    set_status("Escuchando")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_audio:
        tmp_audio.write(audio_value.getvalue())
        audio_path = tmp_audio.name

    # 2. STT
    user_text = transcribe_audio(audio_path)
    os.unlink(audio_path)

    if not user_text:
        set_status("Error: no se reconoció audio")
        st.error("No pude reconocer el audio. Intenta de nuevo, más cerca del micrófono.")
    else:
        st.session_state.messages.append({"role": "user", "content": user_text})
        log("app", f"Usuario dijo: {user_text}")

        # Si el turno anterior dejó una aclaración pendiente (ej. "¿cuál
        # Minecraft querés?"), este turno se usa para resolverla en vez
        # de mandarlo al LLM.
        if st.session_state.pending_app_choice is not None:
            set_status("Pensando")
            reply, resolved = resolve_pending_app_choice(user_text, st.session_state.pending_app_choice)
            if resolved:
                st.session_state.pending_app_choice = None
        else:
            # 1) ¿Es un comando de modelo ("usa phi3", "compara los modelos: ...")?
            model_reply = try_handle_model_command(user_text, st.session_state.chat_client)

            # 2) ¿Es una función del sistema (hora, temporizador, abrir app,
            #    YouTube, calculadora, buscar en internet)?
            function_reply = None if model_reply is not None else try_handle_system_function(
                user_text, lambda msg: None
            )

            if model_reply is not None:
                reply = model_reply
            elif isinstance(function_reply, tuple) and function_reply[0] == "clarify_app":
                _, options = function_reply
                st.session_state.pending_app_choice = options
                opciones = ", ".join(options.keys())
                reply = f"Encontré varias opciones para eso: {opciones}. ¿Cuál de esas querés que abra?"
            elif function_reply is not None:
                reply = function_reply
            else:
                # 3. PENSANDO -> LLM
                set_status("Pensando")
                with st.spinner("Kry está pensando..."):
                    reply = st.session_state.chat_client.ask(user_text)

        st.session_state.messages.append({"role": "assistant", "content": reply})

        # 4. RESPONDIENDO -> TTS
        set_status("Respondiendo")
        audio_out_path = os.path.join(tempfile.gettempdir(), "jarvis_reply.mp3")
        result_path = text_to_speech(reply, output_path=audio_out_path)

        if result_path:
            st.audio(result_path, autoplay=True)
        else:
            st.warning("No se pudo generar el audio de la respuesta, pero aquí está el texto.")

        set_status("En espera")

# --- Historial de conversación ---
st.subheader("Conversación")
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# --- Controles ---
if st.button("Reiniciar conversación"):
    st.session_state.chat_client.reset()
    st.session_state.messages = []
    set_status("En espera")
    st.rerun()
