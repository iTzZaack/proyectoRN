"""
model_commands.py
Comandos de voz para el requisito opcional "Selección entre varios
modelos LLM o comparación de respuestas entre modelos".

Se revisan ANTES que las funciones del sistema y antes del LLM normal:
- "usa phi3" / "cambia al modelo llama" -> cambia el modelo activo de
  Kry sin perder la memoria de la conversación.
- "compara los modelos: ¿qué es un transformer?" -> le hace la misma
  pregunta a TODOS los modelos disponibles y devuelve las respuestas
  de cada uno, sin tocar la memoria principal de la charla.

Es ideal para la sustentación (sección 12 del PDF: "¿Qué diferencia
hay entre el modelo que usaste y un modelo base...?"): podés mostrar
en vivo cómo responde distinto phi3:mini (más chico) vs llama3.1:8b
(más grande) a la misma pregunta.
"""
import re
from config import AVAILABLE_MODELS

# Alias coloquiales para nombrar cada modelo por voz, sin tener que
# decir el nombre técnico completo ("phi3:mini").
_ALIASES = {
    "phi3:mini": ["phi3", "phi 3", "phi", "el chico", "el liviano", "el rápido"],
    "llama3.1:8b": ["llama", "llama3", "llama 3", "llama 3.1", "llama tres uno",
                     "el grande", "el pesado", "el ocho b"],
}


def _match_model(fragment: str) -> str | None:
    f = fragment.lower()
    for model in AVAILABLE_MODELS:
        if model.lower() in f:
            return model
        for alias in _ALIASES.get(model, []):
            if alias in f:
                return model
    return None


def try_handle_model_command(text: str, chat_client):
    """
    Devuelve una respuesta (str) si el texto era un comando de cambio o
    comparación de modelo, o None si debe seguir el flujo normal.
    """
    t = text.lower().strip()
    t = re.sub(r"[¿?¡!.,;:]", "", t)

    # --- Comparar modelos ---
    m = (
        re.search(r"\bcompara(?:r)?\s+(?:los\s+)?modelos?\s*[:\-]?\s*(.+)$", t)
        or re.search(r"\bpregunta(?:le)?\s+a\s+los\s+dos\s+modelos\s*[:\-]?\s*(.+)$", t)
        or re.search(r"\bqué\s+dicen\s+los\s+dos\s+modelos\s+(?:sobre|de)\s+(.+)$", t)
    )
    if m:
        question = m.group(1).strip()
        if not question:
            return "Decime qué pregunta querés que les haga a los modelos para comparar."
        partes = []
        for model in AVAILABLE_MODELS:
            respuesta = chat_client.ask_with_model(model, question)
            partes.append(f"Según {model}: {respuesta}")
        return " ... ".join(partes)

    # --- Cambiar de modelo activo ---
    if re.search(r"\b(usa|cambia|cambiate|activa|activá)\b.*\bmodelo\b", t) or \
       re.search(r"\b(usa|cambia|cambiate a|activa)\s+(phi3|phi|llama)", t):
        model = _match_model(t)
        if model:
            chat_client.switch_model(model)
            return f"Listo, ahora estoy pensando con el modelo {model}."
        disponibles = ", ".join(AVAILABLE_MODELS)
        return f"No reconocí ese modelo. Los que tengo disponibles son: {disponibles}."

    return None
