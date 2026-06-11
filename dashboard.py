import requests
import json
import random
import time
import urllib.parse
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
import os
from deep_translator import GoogleTranslator

# ============================================================
# CONFIGURACIÓN
# ============================================================
CALLMEBOT_API_KEY = os.environ.get("CALLMEBOT_API_KEY")
TELEFONO = os.environ.get("TELEFONO")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
NOTICIAS_MAX = 10

LATITUD = "20.0205"
LONGITUD = "-98.7865"

# Límite REAL: CallMeBot hace GET, la URL completa no debe superar ~2000 chars.
# El texto codificado ocupa la mayor parte. Con emojis/tildes, 1 char => hasta 9 chars en URL.
# Usamos 400 chars de texto como límite conservador para estar seguros.
LIMITE_CHARS_TEXTO = 400

translator = GoogleTranslator(source='en', target='es')


# ============================================================
# UTILIDAD: División de mensajes a prueba de cortes
# ============================================================
def dividir_en_bloques(texto: str, limite: int = LIMITE_CHARS_TEXTO) -> list[str]:
    """
    Divide el texto en partes que, una vez URL-encoded, nunca superan
    el límite seguro de CallMeBot.

    Estrategia:
      1. Intentar respetar saltos de línea (no cortar a mitad de una línea).
      2. Si una sola línea supera el límite, cortarla por espacios.
      3. Verificar SIEMPRE con len(urllib.parse.quote(parte)) antes de aceptar.
    """
    def encoded_len(s: str) -> int:
        return len(urllib.parse.quote(s))

    # Límite en chars codificados (cada char puede ser hasta 9 en URL)
    limite_encoded = limite * 3  # ~1200, conservador

    lineas = texto.splitlines(keepends=True)
    bloques = []
    actual = ""

    for linea in lineas:
        candidato = actual + linea

        if encoded_len(candidato) <= limite_encoded:
            actual = candidato
        else:
            # Guardar lo acumulado si hay algo
            if actual.strip():
                bloques.append(actual.rstrip("\n"))

            # ¿La línea sola cabe?
            if encoded_len(linea) <= limite_encoded:
                actual = linea
            else:
                # Línea muy larga: cortar por palabras
                palabras = linea.split(" ")
                actual = ""
                for palabra in palabras:
                    prueba = actual + (" " if actual else "") + palabra
                    if encoded_len(prueba) <= limite_encoded:
                        actual = prueba
                    else:
                        if actual.strip():
                            bloques.append(actual)
                        actual = palabra

    if actual.strip():
        bloques.append(actual.rstrip("\n"))

    return bloques


# ============================================================
# 1. POEMA
# ============================================================
def obtener_poema() -> tuple[str, str]:
    fallbacks = [
        ("El arte y la paciencia todo lo alcanzan.", "Anónimo"),
        ("Nada es tuyo, salvo el tiempo.", "Séneca"),
        ("Tarde o temprano, el que busca halla.", "Anónimo"),
    ]
    try:
        resp = requests.get(
            "https://poetrydb.org/random/1",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()[0]
            lineas = [l for l in data["lines"] if l.strip()][:4]
            texto_original = "\n".join(lineas)
            if len(texto_original) > 10:
                texto_traducido = translator.translate(texto_original)
            else:
                texto_traducido = texto_original
            return texto_traducido, data["author"]
    except Exception as e:
        print(f"[poema] Error: {e}")
    return random.choice(fallbacks)


# ============================================================
# 2. FRASE
# ============================================================
def obtener_frase() -> tuple[str, str]:
    fallbacks = [
        ("El éxito es la suma de pequeños esfuerzos repetidos día tras día.", "Robert Collier"),
        ("No cuentes los días; haz que los días cuenten.", "Muhammad Ali"),
        ("La vida es lo que pasa mientras estás ocupado haciendo otros planes.", "John Lennon"),
    ]
    try:
        resp = requests.get(
            "https://zenquotes.io/api/random",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if resp.status_code == 200:
            q = resp.json()[0]
            texto_traducido = translator.translate(q["q"])
            return texto_traducido, q["a"]
    except Exception as e:
        print(f"[frase] Error: {e}")
    return random.choice(fallbacks)


# ============================================================
# 3. NOTICIAS
# ============================================================
NOTICIAS_TIMEOUT_NAV  = 30000   # ms para page.goto  (subido de 20s a 30s)
NOTICIAS_TIMEOUT_SEL  = 15000   # ms para wait_for_selector
NOTICIAS_REINTENTOS   = 2       # intentos por sección si hay timeout

def _scrape_seccion(page, sec: dict) -> list[dict]:
    """Extrae noticias de una sección. Lanza excepción si falla."""
    response = page.goto(sec["url"], timeout=NOTICIAS_TIMEOUT_NAV)
    print(f"  HTTP {response.status if response else '?'}")

    # Esperar con scroll suave para forzar carga lazy
    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
    page.wait_for_selector("article a", timeout=NOTICIAS_TIMEOUT_SEL)

    elementos = page.query_selector_all("article a")
    print(f"  {len(elementos)} elementos encontrados.")

    noticias = []
    count = vacios = cortos = 0
    for el in elementos:
        titulo = el.inner_text().strip()
        if not titulo:
            vacios += 1
            continue
        if len(titulo) <= 10:
            cortos += 1
            continue
        if count < NOTICIAS_MAX:
            noticias.append({"icono": sec["icono"], "titulo": titulo, "seccion": sec["nombre"]})
            count += 1

    print(f"  {count} guardadas | {vacios} vacías | {cortos} cortas.")
    return noticias


def obtener_noticias() -> str:
    secciones = [
        {"url": "https://www.elsoldehidalgo.com.mx/local/",   "icono": "📍", "nombre": "Local"},
        {"url": "https://www.elsoldehidalgo.com.mx/turismo/", "icono": "🎉", "nombre": "Turismo"},
    ]
    todas = []

    print("\n--- INICIANDO EXTRACCIÓN DE NOTICIAS ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        for sec in secciones:
            print(f"\n➤ {sec['nombre']}")
            exito = False

            for intento in range(1, NOTICIAS_REINTENTOS + 1):
                # Página nueva por cada intento para evitar estado sucio
                page = browser.new_page()
                try:
                    print(f"  Intento {intento}/{NOTICIAS_REINTENTOS}...")
                    noticias = _scrape_seccion(page, sec)
                    todas.extend(noticias)
                    exito = True
                    break
                except Exception as e:
                    print(f"  ⚠️  {type(e).__name__}: {str(e)[:120]}")
                    if intento < NOTICIAS_REINTENTOS:
                        print(f"  Reintentando en 3 s...")
                        time.sleep(3)
                finally:
                    page.close()

            if not exito:
                print(f"  ❌ No se pudo obtener sección '{sec['nombre']}' tras {NOTICIAS_REINTENTOS} intentos.")

        browser.close()

    if not todas:
        return "• No se pudieron obtener noticias hoy."

    resultado = ""
    for seccion in ["Local", "Turismo"]:
        noticias_sec = [n for n in todas if n["seccion"] == seccion]
        if noticias_sec:
            resultado += f"*{seccion}*\n"
            for n in noticias_sec:
                resultado += f"{n['icono']} {n['titulo']}\n"
            resultado += "\n"
    return resultado.strip()


# ============================================================
# 4. CLIMA
# ============================================================
def obtener_clima() -> str:
    url = (
        f"https://api.openweathermap.org/data/2.5/forecast"
        f"?lat={LATITUD}&lon={LONGITUD}&appid={OPENWEATHER_API_KEY}"
        f"&units=metric&lang=es"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[clima] Error: {e}")
        return "⚠️ No se pudo obtener el pronóstico."

    temp_max = -999
    temp_min = 999
    viento_max = 0
    frecuencias_desc: dict[str, int] = {}
    ventanas_lluvia = []
    dentro_alerta = False
    hora_inicio = hora_fin = ""
    prob_pico = 0

    for i in range(8):
        p = data["list"][i]
        dt_utc = datetime.strptime(p["dt_txt"], "%Y-%m-%d %H:%M:%S")
        hora_local = dt_utc - timedelta(hours=6)
        hora_texto = hora_local.strftime("%I:%M %p").lstrip("0").replace(" 0", " ")

        temp_max = max(temp_max, p["main"]["temp_max"])
        temp_min = min(temp_min, p["main"]["temp_min"])
        viento_kmh = p["wind"]["speed"] * 3.6
        viento_max = max(viento_max, viento_kmh)
        desc = p["weather"][0]["description"]
        frecuencias_desc[desc] = frecuencias_desc.get(desc, 0) + 1
        prob_lluvia = round(p["pop"] * 100)

        if prob_lluvia >= 38:
            if not dentro_alerta:
                dentro_alerta = True
                hora_inicio = hora_texto
                prob_pico = prob_lluvia
            else:
                prob_pico = max(prob_pico, prob_lluvia)
            hora_fin = hora_texto
        else:
            if dentro_alerta:
                ventanas_lluvia.append(
                    f"⏳ {hora_inicio} a {hora_fin} | Pico: {prob_pico}% 🌧️"
                )
                dentro_alerta = False
                prob_pico = 0

    if dentro_alerta:
        ventanas_lluvia.append(
            f"⏳ {hora_inicio} en adelante | Pico: {prob_pico}% 🌧️"
        )

    desc_predominante = (
        max(frecuencias_desc, key=frecuencias_desc.get).capitalize()
        if frecuencias_desc
        else "Despejado"
    )

    SEP = "━━━━━━━━━━━━━━━━━━━━"
    clima_msg = (
        f"⚡ *CLIMA* ⚡\n{SEP}\n"
        f"🌤 {desc_predominante}\n"
        f"🌡️ {round(temp_min)}°C – {round(temp_max)}°C\n"
        f"💨 Ráfagas: {round(viento_max)} km/h\n\n"
        f"🚨 *ALERTAS DE LLUVIA:*\n"
    )

    if ventanas_lluvia:
        clima_msg += "\n".join(ventanas_lluvia)
        clima_msg += "\n\n⚠️ Organiza actividades al exterior fuera de estos horarios."
    else:
        clima_msg += "🟢 Sin lluvia significativa (<38%) las próximas 24 h. ¡Excelente día! 😎"

    return clima_msg


# ============================================================
# 5. CHISTE
# ============================================================
def obtener_chiste() -> str:
    try:
        resp = requests.get(
            "https://v2.jokeapi.dev/joke/Any?lang=es&type=single&blacklistFlags=nsfw,racist,sexist",
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if not data.get("error") and data.get("joke"):
                return data["joke"]
    except Exception as e:
        print(f"[chiste] Error: {e}")
    return "Programar es 10% escribir código y 90% entender por qué no funciona. 💻"


# ============================================================
# 6. VERSÍCULO DEL DÍA
# ============================================================
_VERSICULOS_FALLBACK = [
    ("Filipenses 4:13",  "Todo lo puedo en Cristo que me fortalece."),
    ("Jeremías 29:11",   "Yo sé los planes que tengo para ustedes: planes de bienestar y no de calamidad, para darles un futuro y una esperanza."),
    ("Isaías 40:31",     "Los que esperan en el Señor renovarán sus fuerzas; volarán como águilas."),
    ("Salmos 23:1",      "El Señor es mi pastor; nada me faltará."),
    ("Proverbios 3:5",   "Confía en el Señor con todo tu corazón y no te apoyes en tu propia prudencia."),
    ("Mateo 6:34",       "No se preocupen por el mañana; el mañana se preocupará por sí mismo."),
    ("Romanos 8:28",     "Sabemos que Dios dispone todas las cosas para el bien de quienes lo aman."),
]

_REFERENCIAS = [
    "john+3:16", "psalms+23:1", "philippians+4:13", "jeremiah+29:11",
    "isaiah+40:31", "romans+8:28", "proverbs+3:5-6", "matthew+6:33",
    "joshua+1:9",  "psalm+46:1",  "john+14:6",       "romans+12:2",
    "1corinthians+13:4-5", "ephesians+2:8", "james+1:2-3",
]

def obtener_versiculo() -> tuple[str, str]:
    """
    Devuelve (texto, referencia) usando bible-api.com (gratuita, sin key).
    Traduce al español si el texto viene en inglés.
    """
    referencia = random.choice(_REFERENCIAS)
    try:
        resp = requests.get(
            f"https://bible-api.com/{referencia}?translation=kjv",
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            texto_en = data.get("text", "").strip().replace("\n", " ")
            ref      = data.get("reference", referencia)
            if texto_en:
                texto_es = translator.translate(texto_en)
                return texto_es, ref
    except Exception as e:
        print(f"[versiculo] Error: {e}")

    ref_fb, texto_fb = random.choice(_VERSICULOS_FALLBACK)
    return texto_fb, ref_fb


# ============================================================
# 7. CONSTRUIR SECCIONES INDEPENDIENTES
# ============================================================
SEP = "━━━━━━━━━━━━━━━━━━━━"

def construir_secciones(
    poema_texto, poema_autor,
    frase_texto, frase_autor,
    noticias_texto,
    clima_texto,
    chiste_texto,
    versiculo_texto, versiculo_ref,
) -> list[str]:
    hoy = datetime.now().strftime("%A %d de %B")

    secciones = [
        # Encabezado + versículo + poema + frase
        (
            f"🌅 *Buenos días — {hoy}*\n{SEP}\n"
            f"✝️ *ORACIÓN DEL DÍA*\n_{versiculo_texto}_\n"
            f"    📖 _{versiculo_ref}_\n\n"
            f"🌹 *VERSOS DEL DÍA*\n_{poema_texto}_\n"
            f"    ✍️ _— {poema_autor}_\n\n"
            f"🧠 *REFLEXIÓN*\n\"{frase_texto}\"\n"
            f"    ✍️ _— {frase_autor}_"
        ),
        # Noticias
        f"📰 *NOTICIAS DE HIDALGO*\n{SEP}\n{noticias_texto}",
        # Clima
        clima_texto,
        # Cierre
        f"😄 *MOMENTO DE RELAX*\n_{chiste_texto}_\n{SEP}\n✨ _¡Que tengas un gran día!_",
    ]
    return secciones


# ============================================================
# 7. ENVIAR WHATSAPP
# ============================================================
def enviar_whatsapp(mensaje: str) -> bool:
    """Envía un mensaje. Devuelve True si tuvo éxito."""
    texto_codificado = urllib.parse.quote(mensaje)
    url = (
        f"https://api.callmebot.com/whatsapp.php"
        f"?phone={TELEFONO}&apikey={CALLMEBOT_API_KEY}&text={texto_codificado}"
    )
    # Verificación de longitud total de URL
    if len(url) > 2000:
        print(f"⚠️  URL demasiado larga ({len(url)} chars). Este bloque se subdividirá.")
        return False
    try:
        resp = requests.get(url, timeout=15)
        print(f"  CallMeBot → {resp.status_code}: {resp.text[:80]}")
        return resp.status_code == 200
    except Exception as e:
        print(f"  Error al enviar: {e}")
        return False


# ============================================================
# 8. PIPELINE DE ENVÍO
# ============================================================
def enviar_secciones(secciones: list[str]) -> None:
    """
    Por cada sección lógica:
      - Intenta enviarla entera.
      - Si la URL sería muy larga, la divide y envía cada parte.
    Siempre espera entre envíos para no saturar la API.
    """
    PAUSA = 4  # segundos entre mensajes

    total_enviados = 0
    for idx, seccion in enumerate(secciones, 1):
        print(f"\n📤 Sección {idx}/{len(secciones)}")

        # Verificar si cabe entera
        url_prueba = (
            f"https://api.callmebot.com/whatsapp.php"
            f"?phone={TELEFONO}&apikey={CALLMEBOT_API_KEY}"
            f"&text={urllib.parse.quote(seccion)}"
        )

        if len(url_prueba) <= 2000:
            partes = [seccion]
        else:
            print(f"  ↳ Sección muy larga ({len(url_prueba)} chars en URL), dividiendo...")
            partes = dividir_en_bloques(seccion)
            print(f"  ↳ Dividida en {len(partes)} partes.")

        for j, parte in enumerate(partes, 1):
            print(f"  Enviando parte {j}/{len(partes)} ({len(parte)} chars de texto)...")
            exito = enviar_whatsapp(parte)
            if not exito:
                # Último recurso: subdividir aún más
                print(f"  ⚠️  Fallo. Intentando con bloques más pequeños...")
                sub_partes = dividir_en_bloques(parte, limite=200)
                for k, sub in enumerate(sub_partes, 1):
                    print(f"    Sub-parte {k}/{len(sub_partes)}...")
                    enviar_whatsapp(sub)
                    if k < len(sub_partes):
                        time.sleep(PAUSA)
            total_enviados += 1
            if total_enviados > 1 or j < len(partes):
                time.sleep(PAUSA)

    print(f"\n✅ Envío completo. {total_enviados} mensaje(s) enviado(s).")


# ============================================================
# 9. MAIN
# ============================================================
def main():
    print("🌅 Iniciando bot de buenos días...\n")

    print("✝️  Obteniendo versículo...")
    versiculo_texto, versiculo_ref = obtener_versiculo()

    print("📖 Obteniendo poema...")
    poema_texto, poema_autor = obtener_poema()

    print("💡 Obteniendo frase...")
    frase_texto, frase_autor = obtener_frase()

    print("📰 Obteniendo noticias...")
    noticias_texto = obtener_noticias()

    print("🌤  Obteniendo clima...")
    clima_texto = obtener_clima()

    print("😄 Obteniendo chiste...")
    chiste_texto = obtener_chiste()

    secciones = construir_secciones(
        poema_texto, poema_autor,
        frase_texto, frase_autor,
        noticias_texto,
        clima_texto,
        chiste_texto,
        versiculo_texto, versiculo_ref,
    )

    # Log completo para debugging
    with open("mensaje.log", "w", encoding="utf-8") as f:
        for i, s in enumerate(secciones, 1):
            f.write(f"=== SECCIÓN {i} ===\n{s}\n\n")

    print(f"\n📨 {len(secciones)} secciones listas para enviar.")
    enviar_secciones(secciones)


if __name__ == "__main__":
    main()
