"""
system_functions.py
Funciones reales que Kry puede ejecutar directamente en la
computadora, sin pasar por el LLM.
"""
import re
import os
import glob
import difflib
import subprocess
import threading
import time
import webbrowser
import datetime
import pyautogui

try:
    import pyperclip
except ImportError:
    pyperclip = None

# Apps del sistema
_APPS = {
    "calculadora": "calc.exe",
    "bloc de notas": "notepad.exe",
    "notas": "notepad.exe",
    "explorador de archivos": "explorer.exe",
    "paint": "mspaint.exe",
    "chrome": "chrome",
    "google chrome": "chrome",
    "opera": "opera",
}

_BROWSER_ALIASES = {
    "opera": "opera",
    "ópera": "opera",
    "chrome": "chrome",
    "edge": "edge",
    "brave": "brave",
}


def _detect_browser(t: str) -> str | None:
    return next((canon for alias, canon in _BROWSER_ALIASES.items() if alias in t), None)

_active_timers = []


# --------------------------------------------------------------------
# Índice dinámico de aplicaciones instaladas (Menú Inicio de Windows)
# --------------------------------------------------------------------

_app_index = None


def _start_menu_dirs() -> list[str]:
    dirs = []
    programdata = os.environ.get("PROGRAMDATA")
    appdata = os.environ.get("APPDATA")
    if programdata:
        dirs.append(os.path.join(programdata, r"Microsoft\Windows\Start Menu\Programs"))
    if appdata:
        dirs.append(os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs"))
    return [d for d in dirs if os.path.isdir(d)]


def _build_app_index() -> dict:
    index = {}
    for base in _start_menu_dirs():
        pattern = os.path.join(base, "**", "*.lnk")
        for path in glob.glob(pattern, recursive=True):
            name = os.path.splitext(os.path.basename(path))[0]
            index.setdefault(name, path)
    return index


def _get_app_index() -> dict:
    global _app_index
    if _app_index is None:
        _app_index = _build_app_index()
    return _app_index


def refresh_app_index():
    global _app_index
    _app_index = _build_app_index()


def _find_app_matches(query: str) -> dict:
    index = _get_app_index()
    q = query.lower().strip()
    if not q:
        return {}

    matches = {name: path for name, path in index.items() if q in name.lower()}

    if not matches:
        close = difflib.get_close_matches(q, [n.lower() for n in index.keys()], n=5, cutoff=0.6)
        matches = {name: path for name, path in index.items() if name.lower() in close}

    return matches


def _open_by_path(display_name: str, path: str) -> str:
    try:
        os.startfile(path)
        return f"Abriendo {display_name}."
    except Exception as exc:
        return f"No pude abrir {display_name}: {exc}"


def _open_app(name: str):
    name_l = name.lower().strip()

    if name_l in _APPS:
        try:
            subprocess.Popen(_APPS[name_l], shell=True)
            return f"Abriendo {name}."
        except Exception as exc:
            return f"No pude abrir {name}: {exc}"

    matches = _find_app_matches(name_l)

    if not matches:
        return f"No encontré ninguna aplicación instalada que se llame '{name}'."

    if len(matches) == 1:
        display_name, path = next(iter(matches.items()))
        return _open_by_path(display_name, path)

    return ("clarify_app", matches)


def resolve_pending_app_choice(user_text: str, pending_options: dict):
    t = user_text.lower().strip()
    t = re.sub(r"[¿?¡!.,;:]", "", t)

    candidates = {name: path for name, path in pending_options.items() if t in name.lower() or name.lower() in t}

    if not candidates:
        close = difflib.get_close_matches(t, [n.lower() for n in pending_options.keys()], n=3, cutoff=0.5)
        candidates = {name: path for name, path in pending_options.items() if name.lower() in close}

    if len(candidates) == 1:
        display_name, path = next(iter(candidates.items()))
        return _open_by_path(display_name, path), True

    if len(candidates) > 1:
        opciones = ", ".join(candidates.keys())
        return f"Sigue sin quedarme claro, tenemos: {opciones}. ¿Cuál de esas?", False

    return "No reconocí ninguna de las opciones anteriores, cancelo la apertura.", True


def _current_time() -> str:
    now = datetime.datetime.now().strftime("%H:%M")
    return f"Son las {now}."


def _current_date() -> str:
    now = datetime.datetime.now().strftime("%d de %B de %Y")
    return f"Hoy es {now}."


def _web_search(query: str, browser: str | None = None) -> str:
    url = "https://www.google.com/search?q=" + query.replace(" ", "+")
    _open_url(url, browser)
    donde = f" en {browser}" if browser else ""
    return f"Busqué '{query}' en Google{donde}."


def _open_website(target: str, browser: str | None = None) -> str:
    t = target.strip().lower()
    t = t.replace(" punto com", ".com").replace(" punto ", ".")
    t = t.replace(" ", "")

    if not t:
        return "No entendí bien qué página querés que abra."

    if t.startswith("http://") or t.startswith("https://"):
        url = t
    else:
        if "." not in t:
            t = f"{t}.com"
        url = f"https://{t}"

    _open_url(url, browser)
    donde = f" en {browser}" if browser else ""
    return f"Abriendo {url}{donde}."


def _open_url(url: str, browser: str | None = None) -> None:
    if browser:
        try:
            subprocess.Popen(f'start "" {browser} "{url}"', shell=True)
            return
        except Exception as exc:
            print(f"[system_functions] No pude abrir {browser} puntualmente, uso el predeterminado: {exc}")
    webbrowser.open(url)


def _search_youtube_first(query: str) -> str | None:
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "default_search": "ytsearch1",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch1:{query}", download=False)
        entries = (info or {}).get("entries") or []
        if entries:
            video_id = entries[0].get("id")
            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"
    return None


def _play_youtube(query: str, browser: str | None = None) -> str:
    try:
        video_url = _search_youtube_first(query)
        if video_url:
            _open_url(video_url, browser)
            donde = f" en {browser}" if browser else ""
            return f"Ya está sonando '{query}' en YouTube{donde}."
    except Exception as exc:
        print(f"[system_functions] Búsqueda directa en YouTube falló, uso resultados normales: {exc}")

    url = "https://www.youtube.com/results?search_query=" + query.replace(" ", "+")
    _open_url(url, browser)
    donde = f" en {browser}" if browser else ""
    return f"Te dejé la búsqueda de '{query}' abierta en YouTube{donde}, elegí el video que quieras."


# --------------------------------------------------------------------
# Normalización matemática y cálculo
# --------------------------------------------------------------------

def _normalize_math_expression(raw: str) -> str:
    """Extrae la expresión matemática sustituyendo palabras por números y operadores."""
    t = raw.lower()
    
    # Eliminar palabras de orden antes de procesar
    t = re.sub(r"\b(suma|sumar|resta|restar|multiplica|divide|calcula|resuelve)\b", "", t)

    # Mapeo estricto de operadores hablados
    t = re.sub(r"\b(más|mas)\b", "+", t)
    t = re.sub(r"\bmenos\b", "-", t)
    t = re.sub(r"\bpor\b", "*", t)
    t = re.sub(r"\b(entre|dividido|dividido entre)\b", "/", t)

    num_map = {
        "cero": "0", "uno": "1", "dos": "2", "tres": "3", "cuatro": "4",
        "cinco": "5", "seis": "6", "siete": "7", "ocho": "8", "nueve": "9",
        "diez": "10", "once": "11", "doce": "12", "trece": "13", "catorce": "14",
        "quince": "15", "dieciséis": "16", "diecisiete": "17", "dieciocho": "18",
        "diecinueve": "19", "veinte": "20", "veintiuno": "21", "veintidós": "22",
        "veintidos": "22", "treinta": "30", "cuarenta": "40", "cincuenta": "50",
        "cien": "100"
    }

    for word, digit in num_map.items():
        t = re.sub(rf"\b{word}\b", digit, t)

    # Filtrar solo números y símbolos matemáticos válidos
    t = re.sub(r"[^0-9\.\+\-\*/\(\)]", "", t)
    return t.strip()


def _run_calculation(expression: str) -> str:
    """Resuelve la cuenta matemáticamente y la pega directamente en la Calculadora de Windows."""
    resultado = None
    try:
        allowed_chars = set("0123456789.+-*/() ")
        if expression and set(expression) <= allowed_chars:
            resultado = eval(expression, {"__builtins__": {}}, {})
    except Exception:
        resultado = None

    visual_ok = True
    try:
        # Abrir la calculadora
        subprocess.Popen("calc.exe", shell=True)
        time.sleep(1.2)  # Dar tiempo a Windows para que la ventana tome foco

        # Copiar al portapapeles para evitar errores de layout de teclado (+ mapeado como *)
        if pyperclip:
            pyperclip.copy(expression)
        else:
            # Fallback nativo usando clip de Windows
            process = subprocess.Popen('clip', stdin=subprocess.PIPE, close_fds=True, shell=True)
            process.communicate(input=expression.encode('utf-16le'))

        # Pegar directamente en la Calculadora (Ctrl+V) y presionar Enter
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.1)
        pyautogui.press('enter')

    except Exception as exc:
        print(f"[system_functions] Error enviando a la Calculadora: {exc}")
        visual_ok = False

    if resultado is not None:
        base = f"La respuesta es {resultado}."
    else:
        base = f"Abrí la calculadora para que hagas {expression}."

    if visual_ok:
        return base + " Ya te la dejé escrita en la Calculadora."
    return base + " No logré escribirlo automáticamente ahí, pero la calculadora ya está abierta."


def _set_timer(minutes: float, on_finish) -> str:
    seconds = minutes * 60

    def _worker():
        time.sleep(seconds)
        on_finish(f"Zaack, se cumplió el temporizador de {minutes} minutos.")

    t = threading.Thread(target=_worker, daemon=True)
    _active_timers.append(t)
    t.start()
    return f"Temporizador de {minutes} minutos iniciado."


def _extract_query(t: str, extra_filler_phrases: list[str] | None = None) -> str:
    cleaned = t
    for phrase in extra_filler_phrases or []:
        cleaned = re.sub(phrase, " ", cleaned)
    cleaned = re.sub(
        r"\b(entra\w*|entrar|anda\w*|ve|abr\w*|pon\w*|reproduc\w*|busc\w*|toc\w*|googl\w*|youtube|google)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\b(a|y|al|que)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def try_handle_system_function(text: str, on_timer_finish):
    t = text.lower().strip()

    t = re.sub(r"[¿?¡!.,;:]", "", t)
    t = re.sub(r"\b(por favor|por fa|porfa|porfavor|please)\b", "", t)
    t = re.sub(r"\s+", " ", t).strip()

    t = re.sub(r"\bbusqu(\w*)\b", r"busca\1", t)
    t = re.sub(r"\btoqu(\w*)\b", r"toca\1", t)
    t = re.sub(r"\breproduzc(\w*)\b", r"reproduce\1", t)

    if re.search(r"\b(qué hora es|dime la hora|hora es)\b", t):
        return _current_time()

    if re.search(r"\b(qué (día|fecha) es|dime la fecha)\b", t):
        return _current_date()

    browser = _detect_browser(t)

    # --- YouTube ---
    if "youtube" in t:
        m = re.search(r"\b(?:pon\w*|reproduc\w*|busc\w*|toc\w*)\s+(.+?)\s+en\s+youtube\b", t)
        if m and m.group(1).strip():
            return _play_youtube(m.group(1).strip(), browser)
        query = _extract_query(t, extra_filler_phrases=[r"\bla canci[oó]n\b", r"\bel video\b", r"\bel tema\b"])
        if query:
            return _play_youtube(query, browser)
        return "Decime qué querés que busque en YouTube."

    # --- Google ---
    if "google" in t or "gould" in t:
        m = re.search(r"\b(?:busc\w*|googl\w*)\s+(.+?)\s+en\s+google\b", t)
        if m and m.group(1).strip():
            return _web_search(m.group(1).strip(), browser)
        query = _extract_query(t)
        if query:
            return _web_search(query, browser)
        return "Decime qué querés que busque en Google."

    # --- Páginas Web ---
    m = re.search(
        r"\b(?:entr\w*|ve|and\w*|met\w*)\s+a\s+(?:la\s+p[aá]gina\s+(?:de|web)?\s*|el\s+sitio\s+(?:de|web)?\s*)?(.+)$",
        t,
    )
    if m and m.group(1).strip():
        return _open_website(m.group(1).strip(), browser)

    m = re.search(r"\babr\w*\s+(?:la\s+p[aá]gina\s+(?:de|web)?\s*|el\s+sitio\s+(?:de|web)?\s*)(.+)$", t)
    if m and m.group(1).strip():
        return _open_website(m.group(1).strip(), browser)

    m = re.search(r"\babr\w*\s+([a-z0-9]+\.(?:com|net|org|es|io|co|gg)\S*)\b", t)
    if m:
        return _open_website(m.group(1).strip(), browser)

    # --- Calculadora y Operaciones ---
    m = re.search(r"\bcalculadora\b\s*(.*)$", t)
    if m and m.group(1).strip():
        expr = _normalize_math_expression(m.group(1))
        if expr:
            return _run_calculation(expr)

    m = re.search(r"\b(?:cu[aá]nto es|calcula|resuelve)\s+(.+)$", t)
    if m:
        expr = _normalize_math_expression(m.group(1))
        if expr:
            return _run_calculation(expr)

    # --- Abrir Apps ---
    m = re.search(r"\babr\w*\s+(?:el|la)?\s*([a-záéíóúñ0-9\s]+)$", t)
    if m:
        app_name = m.group(1).strip()
        if app_name:
            return _open_app(app_name)

    # --- Búsquedas genéricas / Temporizador ---
    m = re.search(r"\bbusc\w*\s+(.+?)\s+en internet\b", t) or re.search(r"\bbusc\w*\s+(.+)$", t)
    if m and "internet" in t:
        return _web_search(m.group(1).strip(), browser)

    m = re.search(r"\btemporizador de (\d+(?:\.\d+)?)\s*minutos?\b", t)
    if m:
        minutes = float(m.group(1))
        return _set_timer(minutes, on_timer_finish)

    return None