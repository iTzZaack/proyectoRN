"""
system_functions.py
Funciones reales que Kry puede ejecutar directamente en la
computadora, sin pasar por el LLM (requisito opcional 5.2:
"Integración con funciones reales: hora, clima, búsqueda web,
control de archivos locales, temporizadores, etc.").

Se detectan por coincidencia de patrones simples en el texto del
usuario ANTES de mandarlo al LLM. Si el texto coincide con una
función, se ejecuta directamente y se devuelve una respuesta corta
(que luego se lee en voz alta), sin gastar tiempo en el modelo.
Si no coincide con ninguna, se deja pasar al flujo normal (LLM).

Nota para el informe técnico: esto es "function calling" implementado
de forma manual con expresiones regulares, en vez de la API de tool
calling del LLM, porque los modelos pequeños locales (phi3/llama3.1
en tamaños chicos) no siempre siguen ese formato de forma confiable;
esta es una decisión de diseño justificable y documentable.

APERTURA DE APLICACIONES
-------------------------
En vez de mantener una lista fija y corta de programas (que obligaba
a hardcodear cada app una por una), se construye un índice dinámico
leyendo los accesos directos del Menú Inicio de Windows (los mismos
.lnk que ves si abrís el menú Inicio y escribís el nombre de un
programa). Esto cubre automáticamente cualquier app instalada:
juegos, launchers (Minecraft, Lunar Client, Steam, etc.), utilidades,
etc., sin tener que editar código cada vez que se instala algo nuevo.

Si el nombre pedido es ambiguo (por ejemplo "abre Minecraft" cuando
hay instalados tanto el launcher oficial como Lunar Client), NO se
abre nada de forma arbitraria: se devuelve una aclaración para que
Kry le pregunte al usuario cuál de las opciones quiere, y el turno
siguiente se resuelve contra esa lista de opciones pendientes
(ver resolve_pending_app_choice).
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

# Apps del sistema que no siempre tienen acceso directo en el Menú
# Inicio (son ejecutables built-in de Windows), así que se mantienen
# como atajos directos y rápidos.
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

# Alias de navegadores tal como puede transcribirlos Whisper (con o sin
# tilde), mapeados al nombre real del ejecutable/comando registrado en
# Windows. Sin esto, "ópera" (con tilde) no matcheaba "opera" y el
# comando `start "" ópera "url"` fallaba en silencio.
_BROWSER_ALIASES = {
    "opera": "opera",
    "ópera": "opera",
    "chrome": "chrome",
    "edge": "edge",
    "brave": "brave",
}


def _detect_browser(t: str) -> str | None:
    return next((canon for alias, canon in _BROWSER_ALIASES.items() if alias in t), None)

_active_timers = []  # referencias para que no las recoja el garbage collector

# --------------------------------------------------------------------
# Índice dinámico de aplicaciones instaladas (Menú Inicio de Windows)
# --------------------------------------------------------------------

_app_index = None  # dict: nombre_visible -> ruta al .lnk (se arma una sola vez, perezoso)


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
    """
    Recorre las carpetas del Menú Inicio y arma {nombre_legible: ruta_lnk}.
    Cubre prácticamente cualquier app instalada normalmente en Windows,
    sin necesidad de mantener una lista manual.
    """
    index = {}
    for base in _start_menu_dirs():
        pattern = os.path.join(base, "**", "*.lnk")
        for path in glob.glob(pattern, recursive=True):
            name = os.path.splitext(os.path.basename(path))[0]
            # Si hay duplicados exactos de nombre, se queda con el primero
            # encontrado (normalmente el de "todos los usuarios").
            index.setdefault(name, path)
    return index


def _get_app_index() -> dict:
    global _app_index
    if _app_index is None:
        _app_index = _build_app_index()
    return _app_index


def refresh_app_index():
    """Fuerza a reconstruir el índice (por si se instaló algo nuevo sin reiniciar Kry)."""
    global _app_index
    _app_index = _build_app_index()


def _find_app_matches(query: str) -> dict:
    """Devuelve {nombre: ruta} de las apps del índice cuyo nombre se parece a `query`."""
    index = _get_app_index()
    q = query.lower().strip()
    if not q:
        return {}

    # 1) Coincidencia por substring (lo más común: "minecraft" adentro
    #    de "Minecraft Launcher" y de "Lunar Client - Minecraft").
    matches = {name: path for name, path in index.items() if q in name.lower()}

    # 2) Si no hay nada literal, se prueba con similitud aproximada
    #    (tolera errores de STT, tildes, etc.).
    if not matches:
        close = difflib.get_close_matches(q, [n.lower() for n in index.keys()], n=5, cutoff=0.6)
        matches = {name: path for name, path in index.items() if name.lower() in close}

    return matches


def _open_by_path(display_name: str, path: str) -> str:
    try:
        os.startfile(path)  # también funciona directo sobre archivos .lnk en Windows
        return f"Abriendo {display_name}."
    except Exception as exc:
        return f"No pude abrir {display_name}: {exc}"


def _open_app(name: str):
    """
    Intenta abrir una aplicación por nombre.
    Devuelve:
      - str: respuesta final (se abrió algo, o no se encontró nada).
      - ("clarify_app", {nombre: ruta, ...}): hay más de una coincidencia,
        Kry debe preguntar cuál antes de abrir nada.
    """
    name_l = name.lower().strip()

    # Atajo rápido para apps built-in de Windows.
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

    # Ambigüedad real (ej. "minecraft" -> launcher oficial + Lunar Client):
    # no se abre nada solo, se pide aclaración.
    return ("clarify_app", matches)


def resolve_pending_app_choice(user_text: str, pending_options: dict):
    """
    Se llama en el turno SIGUIENTE a una aclaración de apps ("¿cuál
    Minecraft querés...?"). Intenta hacer match del texto del usuario
    contra las opciones pendientes (pending_options: {nombre: ruta}).

    Devuelve (respuesta: str, resuelto: bool).
    Si resuelto es False, sigue habiendo ambigüedad o no hubo match y
    quien llama debe decidir si reintenta o cancela.
    """
    t = user_text.lower().strip()
    t = re.sub(r"[¿?¡!.,;:]", "", t)

    # Match directo por substring contra cada opción.
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
    """
    Abre cualquier página web a partir de lo que Zaack diga: un nombre
    de sitio suelto ("wikipedia", "netflix"), un dominio completo
    ("mercadolibre.com") o una URL. Corrige transcripciones habladas
    típicas de Whisper como "punto com" -> ".com".
    """
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
    """
    Abre una URL. Si se pide un navegador puntual (ej. "opera"), se
    intenta abrir específicamente ahí usando el comando 'start' de
    Windows (funciona si ese navegador está instalado, igual que pasa
    hoy con _APPS["opera"]). Si falla o no se pidió ninguno en
    particular, se usa el navegador predeterminado del sistema.
    """
    if browser:
        try:
            subprocess.Popen(f'start "" {browser} "{url}"', shell=True)
            return
        except Exception as exc:
            print(f"[system_functions] No pude abrir {browser} puntualmente, uso el predeterminado: {exc}")
    webbrowser.open(url)


def _search_youtube_first(query: str) -> str | None:
    """
    Usa yt-dlp (mismo motor que youtube-dl, activamente mantenido) para
    resolver el primer resultado de una búsqueda en YouTube SIN
    descargar nada (extract_flat), solo para obtener el video_id real.
    Se prefiere sobre 'youtube-search-python' porque esa librería
    depende de la estructura interna de la página de YouTube y se
    rompe seguido; yt-dlp se actualiza constantemente para seguir
    funcionando.
    """
    import yt_dlp  # import perezoso: no rompe la app si falta la librería

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
    """
    Busca 'query' en YouTube y abre DIRECTO el video (como si Zaack le
    hubiera dado play), en vez de solo mostrar la página de resultados.
    YouTube reproduce automáticamente cualquier video al entrar por URL
    directa (youtube.com/watch?v=...), así que no hace falta que nadie
    haga click. Si algo falla (sin internet, sin yt-dlp instalado,
    etc.), cae de forma segura a abrir la página de resultados.
    """
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


def _normalize_math_expression(raw: str) -> str:
    """Convierte una expresión hablada ('2 más 2', '10 por 3') a notación matemática."""
    t = raw.lower()
    t = re.sub(r"\bmas\b|\bmás\b", "+", t)
    t = re.sub(r"\bmenos\b", "-", t)
    t = re.sub(r"\bpor\b|\bx\b", "*", t)
    t = re.sub(r"\bdividido( entre| por)?\b|\bentre\b", "/", t)
    # se descarta cualquier caracter que no sea número u operador, por
    # seguridad (esto es lo que después se evalúa como cuenta matemática).
    t = re.sub(r"[^0-9\.\+\-\*/\(\)]", "", t)
    return t.strip()


def _run_calculation(expression: str) -> str:
    """
    Abre la Calculadora de Windows y escribe la operación ahí mismo,
    usando automatización de interfaz (pywinauto envía las teclas de
    verdad, como si Zaack las tipeara). Además calcula el resultado por
    dentro y lo dice en voz, para que la respuesta sea correcta aunque
    la parte visual falle (distintas versiones de Windows tienen la
    Calculadora con nombres de ventana levemente distintos).
    """
    resultado = None
    try:
        allowed_chars = set("0123456789.+-*/() ")
        if expression and set(expression) <= allowed_chars:
            resultado = eval(expression, {"__builtins__": {}}, {})  # nosec: charset ya validado arriba
    except Exception:
        resultado = None

    visual_ok = True
    try:
        subprocess.Popen("calc.exe", shell=True)
        time.sleep(1.3)  # darle tiempo a Windows a abrir la ventana

        from pywinauto import Desktop
        from pywinauto.keyboard import send_keys

        win = None
        for candidate in Desktop(backend="uia").windows():
            title = (candidate.window_text() or "").lower()
            if "calculadora" in title or "calculator" in title:
                win = candidate
                break

        if win is None:
            visual_ok = False
        else:
            win.set_focus()
            time.sleep(0.3)
            # En la sintaxis de teclas de pywinauto, '+' es un modificador,
            # así que hay que escribirlo como '{+}' para que se envíe tal
            # cual (los demás operadores no necesitan escape).
            keys = expression.replace("+", "{+}")
            send_keys(keys, pause=0.05)
            send_keys("~")  # '~' equivale a Enter/igual
    except Exception as exc:
        print(f"[system_functions] No pude automatizar la Calculadora: {exc}")
        visual_ok = False

    if resultado is not None:
        base = f"{expression} es igual a {resultado}."
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
    """
    Limpia una frase que menciona "youtube"/"google" en cualquier orden
    ("entra a youtube y busca la canción X", "abre google y busca X")
    quitando verbos, la propia palabra de la plataforma y conectores
    sueltos, para quedarse solo con lo que realmente se quiere buscar.
    No es perfecto (una búsqueda que contenga literalmente la palabra
    "y" o "a" como parte del título puede perder esa palabra), pero
    cubre bien los casos reales de uso por voz.
    """
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
    """
    Revisa si el texto del usuario coincide con una función del sistema.
    Devuelve:
      - None: no coincidió con nada, seguir al flujo normal (LLM).
      - str: respuesta ya ejecutada (leer en voz alta tal cual).
      - ("clarify_app", {nombre: ruta, ...}): hay ambigüedad al abrir una
        app; quien llama debe guardar las opciones y preguntarle al
        usuario, y resolver el turno siguiente con
        resolve_pending_app_choice().

    on_timer_finish: callback(str) que se llama cuando termina un
    temporizador (para que la UI lo anuncie por voz en ese momento).
    """
    t = text.lower().strip()

    # Se limpia puntuación y "muletillas de cortesía" ANTES de aplicar los
    # patrones. Sin esto, algo tan común como "Abre LunarClient, por favor."
    # no matcheaba nada por la coma y el punto, y el mensaje se colaba al
    # LLM (que no sabe que Kry sí puede abrir apps, y termina diciendo
    # que no puede).
    t = re.sub(r"[¿?¡!.,;:]", "", t)
    t = re.sub(r"\b(por favor|por fa|porfa|porfavor|please)\b", "", t)
    t = re.sub(r"\s+", " ", t).strip()

    # El español cambia la CONSONANTE (no solo la terminación) en el
    # subjuntivo de ciertos verbos que se usan mucho después de "quiero
    # que..." o "puedes...": buscar -> busque/busques, tocar ->
    # toque/toques, reproducir -> reproduzca/reproduzcas. Un simple
    # "busc\w*" nunca matchea "busques" porque la c cambió a qu. Se
    # normalizan de vuelta a la raíz base para que los patrones de abajo
    # (que sí usan \w* para las terminaciones regulares) los reconozcan.
    t = re.sub(r"\bbusqu(\w*)\b", r"busca\1", t)
    t = re.sub(r"\btoqu(\w*)\b", r"toca\1", t)
    t = re.sub(r"\breproduzc(\w*)\b", r"reproduce\1", t)

    if re.search(r"\b(qué hora es|dime la hora|hora es)\b", t):
        return _current_time()

    if re.search(r"\b(qué (día|fecha) es|dime la fecha)\b", t):
        return _current_date()

    # NOTA sobre conjugaciones: los patrones de abajo usan \w* en los
    # verbos (busc\w*, pon\w*, reproduc\w*, toc\w*, abr\w*, entr\w*,
    # googl\w*) en vez de la forma fija ("busca", "abre"), porque Zaack
    # (o cualquier usuario) suele pedir las cosas en subjuntivo o con
    # otra persona gramatical: "quiero que abras X y busques Y" usa
    # "abras"/"busques", no "abre"/"busca". Con la forma fija, esas
    # frases no matcheaban nada, el mensaje se colaba al LLM, y el LLM
    # (por su system prompt, que le prohíbe decir "no puedo") terminaba
    # inventando que sí lo había hecho, aunque no ejecutó nada real.

    browser = _detect_browser(t)

    # --- YouTube: se revisa ANTES que "abre X" y que la búsqueda genérica.
    # Si la palabra "youtube" aparece en cualquier parte de la frase, SIEMPRE
    # se trata como pedido de reproducir algo ahí, sin importar el orden en
    # que se dijeron las palabras ("busca X en youtube" O "entra a youtube y
    # busca X" O "abre youtube y pon X" deben funcionar igual). Antes solo
    # se reconocía la forma "verbo + query + en youtube", y frases como
    # "entra a YouTube y busca X" caían por error en el abridor genérico de
    # páginas web, generando una URL pegoteada sin sentido.
    if "youtube" in t:
        m = re.search(r"\b(?:pon\w*|reproduc\w*|busc\w*|toc\w*)\s+(.+?)\s+en\s+youtube\b", t)
        if m and m.group(1).strip():
            return _play_youtube(m.group(1).strip(), browser)
        query = _extract_query(t, extra_filler_phrases=[r"\bla canci[oó]n\b", r"\bel video\b", r"\bel tema\b"])
        if query:
            return _play_youtube(query, browser)
        return "Decime qué querés que busque en YouTube."

    # --- Google: mismo criterio que YouTube arriba: si aparece "google" en
    # cualquier parte de la frase, se interpreta como búsqueda ahí. ---
    if "google" in t:
        m = re.search(r"\b(?:busc\w*|googl\w*)\s+(.+?)\s+en\s+google\b", t)
        if m and m.group(1).strip():
            return _web_search(m.group(1).strip(), browser)
        query = _extract_query(t)
        if query:
            return _web_search(query, browser)
        return "Decime qué querés que busque en Google."

    # --- Abrir cualquier página web / entrar a un sitio: "entra a
    # netflix.com", "ve a wikipedia", "abre la página de mercado libre",
    # "métete a instagram". Se revisa DESPUÉS de youtube/google (arriba),
    # para que esas dos plataformas siempre tengan prioridad y no terminen
    # tratadas como "un sitio web cualquiera". ---
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

    # --- Calculadora: primero el caso "abre la calculadora y haz 15 por 4"
    # (se toma TODO lo que sigue a la palabra "calculadora" y se le pasa a
    # _normalize_math_expression, que ya sabe traducir "por"/"más"/etc. y
    # descartar el resto de las palabras sueltas), después el caso directo
    # "cuánto es 2+2" / "resuelve 2+2". ---
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

    m = re.search(r"\babr\w*\s+(?:el|la)?\s*([a-záéíóúñ0-9\s]+)$", t)
    if m:
        app_name = m.group(1).strip()
        if app_name:
            return _open_app(app_name)

    m = re.search(r"\bbusc\w*\s+(.+?)\s+en internet\b", t) or re.search(r"\bbusc\w*\s+(.+)$", t)
    if m and "internet" in t:
        return _web_search(m.group(1).strip(), browser)

    m = re.search(r"\btemporizador de (\d+(?:\.\d+)?)\s*minutos?\b", t)
    if m:
        minutes = float(m.group(1))
        return _set_timer(minutes, on_timer_finish)

    return None
