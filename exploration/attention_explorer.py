"""
attention_explorer.py
Módulo de exploración teórica pedido por el proyecto (sección 5.1).
Toma un texto de ejemplo y muestra:
  1. Tokenización
  2. Embeddings (dimensión y muestra de valores)
  3. Pesos de self-attention (visualización con matplotlib)

Usa un modelo pequeño de Hugging Face (BERT en español) SOLO para
este módulo de análisis; no es el mismo modelo que genera las
respuestas de JARVIS (ese es el LLM de Ollama).
"""
import matplotlib.pyplot as plt
import torch
from transformers import AutoTokenizer, AutoModel

MODEL_NAME = "dccuchile/bert-base-spanish-wwm-uncased"  # BETO, BERT en español


def explore_text(text: str, layer: int = -1, head: int = 0, save_path: str = "attention.png"):
    """
    Ejecuta el pipeline de exploración sobre un texto de ejemplo.
    Imprime tokenización y embeddings, y guarda una imagen con
    el mapa de atención de una capa/cabeza determinada.
    """
    print(f"\n=== Texto de entrada ===\n{text}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModel.from_pretrained(MODEL_NAME, output_attentions=True)
    model.eval()

    # 1. Tokenización
    inputs = tokenizer(text, return_tensors="pt")
    tokens = tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])
    print(f"\n=== Tokenización ===\n{tokens}")

    # 2. Embeddings
    with torch.no_grad():
        outputs = model(**inputs)
    embeddings = outputs.last_hidden_state  # (batch, seq_len, hidden_dim)
    print(f"\n=== Embeddings ===")
    print(f"Forma: {embeddings.shape}  (tokens x dimensión del vector)")
    print(f"Primeros 5 valores del embedding del primer token:\n{embeddings[0][0][:5]}")

    # 3. Self-attention
    attentions = outputs.attentions  # tupla: (num_layers, batch, num_heads, seq_len, seq_len)
    print(f"\n=== Self-attention ===")
    print(f"Número de capas: {len(attentions)}")
    print(f"Número de cabezas por capa: {attentions[0].shape[1]}")

    attn_matrix = attentions[layer][0, head].detach().numpy()
    _plot_attention(attn_matrix, tokens, layer, head, save_path)
    print(f"\nMapa de atención guardado en: {save_path}")

    return {
        "tokens": tokens,
        "embedding_shape": tuple(embeddings.shape),
        "num_layers": len(attentions),
        "num_heads": attentions[0].shape[1],
        "attention_image": save_path,
    }


def _plot_attention(attn_matrix, tokens, layer, head, save_path):
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(attn_matrix, cmap="viridis")
    ax.set_xticks(range(len(tokens)))
    ax.set_yticks(range(len(tokens)))
    ax.set_xticklabels(tokens, rotation=90)
    ax.set_yticklabels(tokens)
    ax.set_title(f"Self-attention — capa {layer}, cabeza {head}")
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    # Ejemplo de uso directo: python -m exploration.attention_explorer
    explore_text("Oye Kry, enciende las luces del laboratorio.")
