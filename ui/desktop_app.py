"""
Interfaz de escritorio de Kry (Mini-JARVIS) v1.0
Layout rediseñado idéntico a la maqueta de referencia:
- Header oscuro con logo KRY AI v1.0, botón Nuevo Chat + y Selector de Modelo.
- Columna izquierda: Historial de chat con burbujas de estilo elegante e input flotante.
- Columna derecha: Avatar VTuber animado con anillos, estado de habla, barra de onda de audio,
  botón de Mute, temporizador y controles de voz.
"""
import math
import os
import re
import threading
import tempfile
import time
import tkinter as tk
import uuid

import customtkinter as ctk
import pygame
from PIL import Image, ImageTk

from stt.wake_word import listen_for_wake_word
from stt.audio_recorder import record_command
from stt.whisper_stt import transcribe_audio
from tts.edge_tts_engine import text_to_speech
from llm.ollama_client import OllamaChatClient
from utils.logger import log
from utils.system_functions import try_handle_system_function, resolve_pending_app_choice
from utils.sounds import get_listen_tone_path, get_idle_tone_path
from llm.model_commands import try_handle_model_command
from config import (
    WAKE_WORD, CONVERSATION_WINDOW_SECONDS, CONVERSATION_TURN_TIMEOUT,
    AVAILABLE_MODELS, OLLAMA_MODEL,
)

ctk.set_appearance_mode("dark")

# --- Paleta de colores inspirada en la referencia ---
BG_DARK = "#0D0B14"         # Fondo general profundo
HEADER_BG = "#13101C"       # Barra superior
PANEL_BG = "#171422"        # Paneles internos
CARD_BG = "#231E30"         # Botones y contenedores secundarios
BUBBLE_AI = "#201B2E"       # Burbuja Kry
BUBBLE_USER = "#36264F"     # Burbuja Usuario
PURPLE_ACCENT = "#9A5CFF"   # Morado brillante de acento
PURPLE_GLOW = "#7B2CBF"     # Morado medio
PURPLE_DARK = "#3C1661"     # Morado oscuro
TEXT_WHITE = "#F3F0FF"
TEXT_MUTED = "#8E87A3"
RED_ALERT = "#E63946"

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
AVATAR_SIZE = (180, 180)
CANVAS_SIZE = 260

_FRIENDLY_MODEL_NAMES = {
    "llama3.1:8b": "KRY Ultra v1.0 (Llama 3.1 8B)",
    "phi3:mini": "Kry Rápido (phi3)",
}

pygame.mixer.init()


def clean_llm_response(text: str) -> str:
    """Elimina alucinaciones de formato, etiquetas internas y respuestas múltiples."""
    if not text:
        return ""

    # Corta el texto si detecta encabezados Markdown o etiquetas del sistema
    text = re.split(r"(?i)\n\s*#+\s*Instrucci[oó]n|\n\s*#+|\n\s*User:|\n\s*Assistant:", text)[0]

    # Quedarse únicamente con el primer párrafo en caso de que devuelva variaciones
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) > 1:
        text = paragraphs[0]

    return text.strip()


class KryApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("KRY AI v1.0")
        self.geometry("1080x720")
        self.minsize(850, 620)
        self.configure(fg_color=BG_DARK)

        self.chat_client = OllamaChatClient()
        if "llama3.1:8b" in AVAILABLE_MODELS:
            self.chat_client.switch_model("llama3.1:8b")

        self.stop_event = threading.Event()
        self.pause_wakeword_event = threading.Event()
        self.cancel_event = threading.Event()
        self.listening_thread = None
        self.pipeline_busy = False
        self.pending_app_choice = None
        self.awaiting_answer = False

        # Estado del temporizador y audio
        self.is_muted = False
        self.start_time = time.time()
        self.is_speaking = False
        self._bounce_phase = 0.0
        self._mouth_open_now = False

        self._load_avatar_images()
        self._build_ui()
        self._bounce_tick()
        self._update_timer()

    def _load_avatar_images(self):
        closed_path = os.path.join(ASSETS_DIR, "kry_mouth_closed.png")
        open_path = os.path.join(ASSETS_DIR, "kry_mouth_open.png")
        closed_pil = Image.open(closed_path).convert("RGBA").resize(AVATAR_SIZE, Image.LANCZOS)
        open_pil = Image.open(open_path).convert("RGBA").resize(AVATAR_SIZE, Image.LANCZOS)
        self.tk_img_closed = ImageTk.PhotoImage(closed_pil)
        self.tk_img_open = ImageTk.PhotoImage(open_pil)

    def _build_ui(self):
        # ================= HEADER SUPERIOR =================
        header = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0, height=60)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        # Izquierda: Logo v1.0 + Nuevo Chat
        left_header = ctk.CTkFrame(header, fg_color="transparent")
        left_header.pack(side="left", padx=16)

        ctk.CTkLabel(
            left_header, text="KRY AI", font=ctk.CTkFont(family="Arial", size=18, weight="bold"), text_color=TEXT_WHITE
        ).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            left_header, text="v1.0", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        ).pack(side="left", padx=(0, 16))

        new_chat_btn = ctk.CTkButton(
            left_header, text="Nuevo Chat ＋", width=110, height=32,
            fg_color=CARD_BG, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
            corner_radius=8, font=ctk.CTkFont(size=12), command=self.reset_conversation
        )
        new_chat_btn.pack(side="left")

        # Derecha: Selector de Modelo Ollama
        right_header = ctk.CTkFrame(header, fg_color="transparent")
        right_header.pack(side="right", padx=16)

        self._model_display_to_id = {}
        display_values = []
        for model_id in AVAILABLE_MODELS:
            display = _FRIENDLY_MODEL_NAMES.get(model_id, model_id)
            self._model_display_to_id[display] = model_id
            display_values.append(display)
        
        current_model = getattr(self.chat_client, "model", "llama3.1:8b")
        current_display = _FRIENDLY_MODEL_NAMES.get(current_model, current_model)
        if current_display not in display_values:
            display_values.insert(0, current_display)
            self._model_display_to_id[current_display] = current_model

        self.model_menu = ctk.CTkOptionMenu(
            right_header,
            values=display_values,
            command=self._on_model_selected,
            fg_color=CARD_BG,
            button_color=PURPLE_GLOW,
            button_hover_color=PURPLE_ACCENT,
            text_color=TEXT_WHITE,
            dropdown_fg_color=CARD_BG,
            dropdown_hover_color=PURPLE_DARK,
            width=200, height=32, corner_radius=8
        )
        self.model_menu.set(current_display)
        self.model_menu.pack(side="right")

        ctk.CTkLabel(
            right_header, text="Modelo de IA", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        ).pack(side="right", padx=(0, 10))

        # ================= CUERPO PRINCIPAL =================
        body = ctk.CTkFrame(self, fg_color=BG_DARK, corner_radius=0)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        body.grid_columnconfigure(0, weight=6)
        body.grid_columnconfigure(1, weight=5)
        body.grid_rowconfigure(0, weight=1)

        # ---------------- PANEL IZQUIERDO (CHAT) ----------------
        left_panel = ctk.CTkFrame(body, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left_panel.grid_rowconfigure(0, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)

        self.chat_scroll = ctk.CTkScrollableFrame(left_panel, fg_color=PANEL_BG, corner_radius=16)
        self.chat_scroll.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.chat_scroll.grid_columnconfigure(0, weight=1)
        self._chat_row = 0
        self._add_chat_hint()

        # Input de mensaje con botón de enviar alineado
        input_container = ctk.CTkFrame(left_panel, fg_color=PANEL_BG, corner_radius=25, height=50)
        input_container.grid(row=1, column=0, sticky="ew", pady=(0, 2))
        input_container.grid_propagate(False)
        input_container.grid_columnconfigure(0, weight=1)
        input_container.grid_rowconfigure(0, weight=1)

        self.text_entry = ctk.CTkEntry(
            input_container,
            placeholder_text="Escribe tu mensaje...",
            fg_color="transparent",
            border_width=0,
            text_color=TEXT_WHITE,
            placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=13)
        )
        self.text_entry.grid(row=0, column=0, sticky="ew", padx=(18, 6), pady=6)
        self.text_entry.bind("<Return>", self.trigger_text_command)

        self.send_btn = ctk.CTkButton(
            input_container, text="➤", width=36, height=36, corner_radius=18,
            fg_color=PURPLE_ACCENT, hover_color=PURPLE_GLOW,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.trigger_text_command
        )
        self.send_btn.grid(row=0, column=1, padx=(0, 7), pady=7)

        # ---------------- PANEL DERECHO (AVATAR & AUDIOS) ----------------
        right_panel = ctk.CTkFrame(body, fg_color=PANEL_BG, corner_radius=16)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right_panel.grid_rowconfigure(0, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)

        avatar_container = ctk.CTkFrame(right_panel, fg_color="transparent")
        avatar_container.pack(expand=True, fill="both", pady=(15, 0))

        # Canvas para VTuber
        self.avatar_canvas = tk.Canvas(
            avatar_container, width=CANVAS_SIZE, height=CANVAS_SIZE,
            bg=PANEL_BG, highlightthickness=0
        )
        self.avatar_canvas.pack(anchor="center")

        c = CANVAS_SIZE / 2
        self._ring_base_radii = [65, 85, 105]
        self._ring_colors = [PURPLE_ACCENT, PURPLE_GLOW, PURPLE_DARK]
        self._ring_ids = [
            self.avatar_canvas.create_oval(
                c - r, c - r, c + r, c + r, outline=color, width=1.5
            )
            for r, color in zip(self._ring_base_radii, self._ring_colors)
        ]
        self._avatar_item = self.avatar_canvas.create_image(c, c, image=self.tk_img_closed)

        # Indicadores de Estado
        self.status_label = ctk.CTkLabel(
            avatar_container, text="EN ESPERA", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_WHITE
        )
        self.status_label.pack(pady=(10, 2))

        ctk.CTkLabel(
            avatar_container, text="KRY AI", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED
        ).pack(pady=(0, 10))

        # Barra inferior del avatar
        bottom_controls = ctk.CTkFrame(right_panel, fg_color="transparent")
        bottom_controls.pack(fill="x", padx=16, pady=14, side="bottom")

        audio_bar = ctk.CTkFrame(bottom_controls, fg_color=CARD_BG, corner_radius=12, height=44)
        audio_bar.pack(fill="x", pady=(0, 10))
        audio_bar.pack_propagate(False)

        self.record_circle_btn = ctk.CTkButton(
            audio_bar, text="●", width=28, height=28, corner_radius=14,
            fg_color=PURPLE_ACCENT, hover_color=PURPLE_GLOW, text_color=TEXT_WHITE,
            command=self.toggle_listening
        )
        self.record_circle_btn.pack(side="left", padx=8)

        self.wave_canvas = tk.Canvas(audio_bar, width=100, height=20, bg=CARD_BG, highlightthickness=0)
        self.wave_canvas.pack(side="left", fill="x", expand=True, padx=4)
        self._draw_wave_bars(active=False)

        self.mute_btn = ctk.CTkButton(
            audio_bar, text="🎙 Mutear", width=75, height=28, corner_radius=8,
            fg_color=PANEL_BG, hover_color=PURPLE_DARK, text_color=TEXT_WHITE,
            font=ctk.CTkFont(size=11), command=self.toggle_mute
        )
        self.mute_btn.pack(side="left", padx=4)

        self.timer_label = ctk.CTkLabel(
            audio_bar, text="00:00", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        )
        self.timer_label.pack(side="right", padx=(4, 10))

        self.stop_btn = ctk.CTkButton(
            bottom_controls, text="⏹ Detener / Cancelar", height=32,
            fg_color=CARD_BG, hover_color=RED_ALERT, text_color=TEXT_WHITE, corner_radius=8,
            font=ctk.CTkFont(size=12), command=self.cancel_current
        )
        self.stop_btn.pack(fill="x")

        ctk.CTkLabel(
            self, text="Hecho por el Tec. Isaac Jarrin", font=ctk.CTkFont(size=10), text_color=TEXT_MUTED
        ).pack(side="bottom", anchor="se", padx=16, pady=(0, 4))

    def _draw_wave_bars(self, active=False):
        self.wave_canvas.delete("all")
        import random
        num_bars = 16
        width = 100
        height = 20
        bar_w = width / (num_bars * 1.5)
        for i in range(num_bars):
            h = random.randint(4, 18) if active else 3
            x0 = i * (bar_w * 1.5) + 5
            y0 = (height - h) / 2
            x1 = x0 + bar_w
            y1 = y0 + h
            color = PURPLE_ACCENT if active else TEXT_MUTED
            self.wave_canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

    def _update_timer(self):
        elapsed = int(time.time() - self.start_time)
        mins, secs = divmod(elapsed, 60)
        self.timer_label.configure(text=f"{mins:02d}:{secs:02d}")
        if self.is_speaking or self.pipeline_busy:
            self._draw_wave_bars(active=True)
        else:
            self._draw_wave_bars(active=False)
        self.after(500, self._update_timer)

    def toggle_mute(self):
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.mute_btn.configure(text="🔇 Muteado", fg_color=RED_ALERT)
            pygame.mixer.music.set_volume(0.0)
            # Silenciar todos los canales en reproducción inmediatamente
            for i in range(pygame.mixer.get_num_channels()):
                pygame.mixer.Channel(i).set_volume(0.0)
        else:
            self.mute_btn.configure(text="🎙 Mutear", fg_color=PANEL_BG)
            pygame.mixer.music.set_volume(1.0)
            # Restaurar volumen en todos los canales
            for i in range(pygame.mixer.get_num_channels()):
                pygame.mixer.Channel(i).set_volume(1.0)

    def _add_chat_hint(self):
        subtitle = ctk.CTkLabel(
            self.chat_scroll,
            text=f'Escribe tu mensaje abajo o habla usando "{WAKE_WORD.capitalize()}...".',
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        )
        subtitle.grid(row=self._chat_row, column=0, sticky="w", padx=12, pady=(10, 6))
        self._chat_row += 1

    def _on_model_selected(self, display_value: str):
        model_id = self._model_display_to_id.get(display_value, display_value)
        self.chat_client.switch_model(model_id)
        self.append_message("Sistema", f"Modelo cambiado a {display_value}.")
        log("desktop_app", f"Zaack cambió el modelo desde el selector a {model_id}")

    def set_status(self, text: str):
        self.after(0, lambda: self.status_label.configure(text=text.upper()))

    def append_message(self, sender: str, text: str):
        def _append():
            row = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
            row.grid(row=self._chat_row, column=0, sticky="ew", padx=8, pady=6)
            row.grid_columnconfigure(0, weight=1)
            self._chat_row += 1

            if sender == "Zaack":
                bubble = ctk.CTkLabel(
                    row, text=text, justify="left", wraplength=340,
                    fg_color=BUBBLE_USER, text_color=TEXT_WHITE,
                    corner_radius=12, font=ctk.CTkFont(size=13)
                )
                bubble.grid(row=0, column=0, sticky="e", ipadx=12, ipady=8)
            elif sender in ["Kry", "KRY AI"]:
                msg_frame = ctk.CTkFrame(row, fg_color="transparent")
                msg_frame.grid(row=0, column=0, sticky="w")
                
                header_lbl = ctk.CTkLabel(
                    msg_frame, text="KRY AI v1.0", font=ctk.CTkFont(size=10, weight="bold"), text_color=PURPLE_ACCENT
                )
                header_lbl.pack(anchor="w", padx=4, pady=(0, 2))

                bubble = ctk.CTkLabel(
                    msg_frame, text=text, justify="left", wraplength=340,
                    fg_color=BUBBLE_AI, text_color=TEXT_WHITE,
                    corner_radius=12, font=ctk.CTkFont(size=13)
                )
                bubble.pack(anchor="w", ipadx=12, ipady=8)
            else:
                bubble = ctk.CTkLabel(
                    row, text=text, justify="center",
                    text_color=TEXT_MUTED, font=ctk.CTkFont(size=11, slant="italic")
                )
                bubble.grid(row=0, column=0)

            # --- AUTO-SCROLL GARANTIZADO AL FONDO ---
            self.update_idletasks()
            self.chat_scroll._parent_canvas.yview_moveto(1.0)
            self.after(50, lambda: self.chat_scroll._parent_canvas.yview_moveto(1.0))

        self.after(0, _append)

    def _bounce_tick(self):
        self._bounce_phase += 0.22 if self.is_speaking else 0.07
        bounce_amp = 6 if self.is_speaking else 2
        y_offset = bounce_amp * math.sin(self._bounce_phase)

        c = CANVAS_SIZE / 2
        self.avatar_canvas.coords(self._avatar_item, c, c + y_offset)

        ring_amp = 8 if self.is_speaking else 2
        for i, (ring_id, base_r) in enumerate(zip(self._ring_ids, self._ring_base_radii)):
            r = base_r + ring_amp * math.sin(self._bounce_phase * 1.3 + i * 0.8)
            self.avatar_canvas.coords(ring_id, c - r, c - r, c + r, c + r)

        self.after(40, self._bounce_tick)

    def _start_talk_animation(self):
        self.is_speaking = True
        self._mouth_tick()

    def _mouth_tick(self):
        if not self.is_speaking:
            self.avatar_canvas.itemconfig(self._avatar_item, image=self.tk_img_closed)
            return
        self._mouth_open_now = not self._mouth_open_now
        img = self.tk_img_open if self._mouth_open_now else self.tk_img_closed
        self.avatar_canvas.itemconfig(self._avatar_item, image=img)
        self.after(150, self._mouth_tick)

    def _stop_talk_animation(self):
        self.is_speaking = False
        self.avatar_canvas.itemconfig(self._avatar_item, image=self.tk_img_closed)

    def cancel_current(self):
        self.cancel_event.set()
        self.stop_event.set()
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        pygame.mixer.stop()
        self.record_circle_btn.configure(fg_color=PURPLE_ACCENT)
        self.set_status("Cancelado")

    def toggle_listening(self):
        if self.listening_thread and self.listening_thread.is_alive():
            self.stop_event.set()
            self.record_circle_btn.configure(fg_color=PURPLE_ACCENT)
            self.set_status("En espera")
        else:
            self.stop_event.clear()
            self.listening_thread = threading.Thread(target=self._wake_word_loop, daemon=True)
            self.listening_thread.start()
            self.record_circle_btn.configure(fg_color=RED_ALERT)
            self.set_status(f'Escuchando "{WAKE_WORD.capitalize()}"')

    def _wake_word_loop(self):
        while not self.stop_event.is_set():
            listen_for_wake_word(
                stop_event=self.stop_event,
                on_detected=self._on_wake_word_detected,
                on_status=self.set_status,
                pause_event=self.pause_wakeword_event,
            )

    def _on_wake_word_detected(self):
        if self.pipeline_busy:
            return
        self.set_status("Hablando...")
        self._conversation_loop()

    def trigger_text_command(self, event=None):
        if self.pipeline_busy:
            return
        user_text = self.text_entry.get().strip()
        if not user_text:
            return
        self.text_entry.delete(0, "end")

        def _run():
            self.pipeline_busy = True
            self.cancel_event.clear()
            try:
                self.append_message("Zaack", user_text)
                log("desktop_app", f"Zaack escribió: {user_text}")
                self._process_and_respond(user_text)
            except Exception as exc:
                log("desktop_app", f"ERROR en pipeline texto: {exc}")
                self.append_message("Sistema", "Ocurrió un error inesperado.")
            finally:
                self.pipeline_busy = False
                still_listening = bool(self.listening_thread and self.listening_thread.is_alive())
                self.set_status(f'Esperando "{WAKE_WORD.capitalize()}..."' if still_listening else "En espera")

        threading.Thread(target=_run, daemon=True).start()

    def _speak(self, text: str):
        out_path = os.path.join(tempfile.gettempdir(), f"kry_reply_{uuid.uuid4().hex}.wav")
        result_path = text_to_speech(text, output_path=out_path)
        
        if not result_path or not os.path.exists(result_path):
            self.append_message("Sistema", "Error al generar audio de respuesta.")
            return

        if self.cancel_event.is_set():
            return

        self.after(0, self._start_talk_animation)

        try:
            sound = pygame.mixer.Sound(result_path)
            channel = sound.play()

            # Bucle de reproducción actualizando el volumen en tiempo real
            while channel.get_busy():
                if self.cancel_event.is_set():
                    channel.stop()
                    break
                
                # Sincroniza dinámicamente el volumen si el usuario cliquea "Mutear" durante el audio
                channel.set_volume(0.0 if self.is_muted else 1.0)
                time.sleep(0.05)

        except Exception as exc:
            log("desktop_app", f"ERROR reproduciendo audio: {exc}")
        finally:
            self.after(0, self._stop_talk_animation)
            try:
                if os.path.exists(result_path):
                    os.remove(result_path)
            except OSError:
                pass

    def _play_tone(self, path: str):
        if self.is_muted:
            return
        try:
            pygame.mixer.Sound(path).play()
        except Exception as exc:
            log("desktop_app", f"Error reproducir tono: {exc}")

    def _on_timer_finish(self, message: str):
        self.append_message("KRY AI", message)
        threading.Thread(target=self._speak, args=(message,), daemon=True).start()

    def _conversation_loop(self):
        self.pipeline_busy = True
        self.cancel_event.clear()
        try:
            while True:
                if self.cancel_event.is_set():
                    break
                self._run_one_voice_turn()
                if self.cancel_event.is_set():
                    break
                if self.pending_app_choice is None and not self.awaiting_answer:
                    break
        finally:
            self.pipeline_busy = False
            still_listening = bool(self.listening_thread and self.listening_thread.is_alive())
            self.set_status(f'Esperando "{WAKE_WORD.capitalize()}..."' if still_listening else "En espera")
            self._play_tone(get_idle_tone_path())

    def _run_one_voice_turn(self):
        self.awaiting_answer = False
        try:
            self.set_status("Escuchando...")
            self._play_tone(get_listen_tone_path())
            tmp_wav = os.path.join(tempfile.gettempdir(), f"kry_command_{uuid.uuid4().hex}.wav")
            recorded = record_command(tmp_wav, listen_timeout=CONVERSATION_TURN_TIMEOUT)

            if self.cancel_event.is_set() or recorded is None:
                return

            user_text = transcribe_audio(tmp_wav)
            try:
                os.remove(tmp_wav)
            except OSError:
                pass

            if not user_text:
                self.set_status("Sin audio")
                self.append_message("Sistema", "No se reconoció el audio.")
                return

            self.append_message("Zaack", user_text)
            log("desktop_app", f"Zaack dijo: {user_text}")

            if self.cancel_event.is_set():
                return

            self._process_and_respond(user_text)

        except Exception as exc:
            log("desktop_app", f"ERROR en turno de voz: {exc}")
            self.append_message("Sistema", "Ocurrió un error inesperado.")

    def _process_and_respond(self, user_text: str):
        if self.pending_app_choice is not None:
            reply, resolved = resolve_pending_app_choice(user_text, self.pending_app_choice)
            reply = clean_llm_response(reply)
            self.append_message("KRY AI", reply)
            if resolved:
                self.pending_app_choice = None
            self.awaiting_answer = reply.strip().endswith("?")
            if self.cancel_event.is_set():
                return
            self.set_status("Hablando...")
            self._speak(reply)
            return

        model_reply = try_handle_model_command(user_text, self.chat_client)
        function_reply = None if model_reply is not None else try_handle_system_function(
            user_text, self._on_timer_finish
        )

        if model_reply is not None:
            reply = clean_llm_response(model_reply)
            self.append_message("KRY AI", reply)
            self._sync_model_menu()
        elif isinstance(function_reply, tuple) and function_reply[0] == "clarify_app":
            _, options = function_reply
            self.pending_app_choice = options
            opciones = ", ".join(options.keys())
            reply = f"Encontré varias opciones: {opciones}. ¿Cuál abro?"
            self.append_message("KRY AI", reply)
        elif function_reply is not None:
            reply = clean_llm_response(function_reply)
            self.append_message("KRY AI", reply)
        else:
            self.set_status("Pensando...")
            raw_reply = self.chat_client.ask(user_text, cancel_event=self.cancel_event)
            reply = clean_llm_response(raw_reply)
            if self.cancel_event.is_set():
                self.set_status("Cancelado")
                return
            self.append_message("KRY AI", reply)

        self.awaiting_answer = self.pending_app_choice is not None or reply.strip().endswith("?")
        if self.cancel_event.is_set():
            return

        self.set_status("Hablando...")
        self._speak(reply)

    def _sync_model_menu(self):
        display = _FRIENDLY_MODEL_NAMES.get(self.chat_client.model, self.chat_client.model)
        self.after(0, lambda: self.model_menu.set(display))

    def reset_conversation(self):
        self.chat_client.reset()
        for child in list(self.chat_scroll.children.values()):
            child.destroy()
        self._chat_row = 0
        self._add_chat_hint()


if __name__ == "__main__":
    app = KryApp()
    app.mainloop()