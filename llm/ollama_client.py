"""
ollama_client.py
Cliente para el LLM local vía Ollama. Maneja memoria conversacional
(ventana de los últimos N turnos) y manejo de errores.

Requiere tener Ollama instalado y corriendo (`ollama serve`) y el
modelo descargado, por ejemplo: `ollama pull llama3.1`
"""
import ollama
from config import OLLAMA_MODEL, OLLAMA_HOST, MAX_HISTORY_TURNS
from llm.system_prompt import JARVIS_SYSTEM_PROMPT


class OllamaChatClient:
    def __init__(self, model: str = OLLAMA_MODEL, host: str = OLLAMA_HOST):
        self.model = model
        self.client = ollama.Client(host=host)
        self.history: list[dict] = [
            {"role": "system", "content": JARVIS_SYSTEM_PROMPT}
        ]

    def _trim_history(self):
        """Conserva el system prompt + los últimos MAX_HISTORY_TURNS turnos (user+assistant)."""
        system = self.history[0]
        rest = self.history[1:]
        max_messages = MAX_HISTORY_TURNS * 2
        if len(rest) > max_messages:
            rest = rest[-max_messages:]
        self.history = [system] + rest

    def ask(self, user_text: str, temperature: float = 0.7, top_p: float = 0.9,
            cancel_event=None) -> str:
        """
        Envía el texto del usuario al LLM y devuelve la respuesta, usando
        streaming para poder cancelarla a mitad de camino si cancel_event
        se activa (equivalente al botón "detener" de ChatGPT/Gemini).
        Maneja errores de conexión y respuestas vacías sin romper la app.
        """
        if not user_text or not user_text.strip():
            return "No he recibido ningún audio reconocible. ¿Puedes repetirlo?"

        self.history.append({"role": "user", "content": user_text})
        self._trim_history()

        reply_parts = []
        try:
            stream = self.client.chat(
                model=self.model,
                messages=self.history,
                stream=True,
                options={
                    "temperature": temperature,
                    "top_p": top_p,
                    # Antes el límite de tokens era muy bajo y cortaba las
                    # respuestas a mitad de frase. 2048 da margen de sobra
                    # para textos largos (ej. "cuéntame del espacio, dame
                    # un texto full grande") sin cortarse a mitad de frase.
                    "num_predict": 2048,
                },
            )
            for chunk in stream:
                if cancel_event is not None and cancel_event.is_set():
                    break
                piece = chunk.get("message", {}).get("content", "")
                reply_parts.append(piece)
            reply = "".join(reply_parts).strip()
            if not reply:
                reply = "Disculpa, no logré generar una respuesta. ¿Puedes reformular la pregunta?"
        except Exception as exc:
            reply = (
                "Tengo un problema para conectarme con el modelo local. "
                "Verifica que Ollama esté corriendo con 'ollama serve'."
            )
            print(f"[ERROR ollama_client] {exc}")

        self.history.append({"role": "assistant", "content": reply})
        return reply

    def reset(self):
        self.history = [{"role": "system", "content": JARVIS_SYSTEM_PROMPT}]

    def switch_model(self, model: str) -> None:
        """
        Cambia el modelo activo (ej. de phi3:mini a llama3.1:8b) SIN perder
        la memoria de la conversación, para que la charla siga coherente
        aunque cambie el "cerebro" que la procesa. Requisito opcional del
        proyecto: "Selección entre varios modelos LLM".
        """
        self.model = model

    def ask_with_model(self, model: str, user_text: str, temperature: float = 0.7,
                        top_p: float = 0.9) -> str:
        """
        Le hace la misma pregunta a UN modelo puntual, usando el contexto
        de la conversación actual, pero SIN modificar self.history ni
        self.model. Pensado para comparar respuestas entre modelos sin
        que una comparación "ensucie" la memoria principal de Kry.
        Requisito opcional: "comparación de respuestas entre modelos".
        """
        if not user_text or not user_text.strip():
            return "(sin pregunta)"

        temp_messages = self.history + [{"role": "user", "content": user_text}]
        try:
            response = self.client.chat(
                model=model,
                messages=temp_messages,
                stream=False,
                options={"temperature": temperature, "top_p": top_p, "num_predict": 1024},
            )
            reply = response.get("message", {}).get("content", "").strip()
            return reply or "(el modelo no devolvió respuesta)"
        except Exception as exc:
            print(f"[ERROR ollama_client] ask_with_model({model}): {exc}")
            return f"(no se pudo consultar el modelo {model}: puede que no esté descargado)"
