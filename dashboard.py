import requests
import json
import random
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
import os

# ============================================================
# CONFIGURACIÓN (variables de entorno)
# ============================================================
CALLMEBOT_API_KEY = os.environ.get("CALLMEBOT_API_KEY")
TELEFONO = os.environ.get("TELEFONO")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")  # ← Nueva
NOTICIAS_MAX = 3

# Coordenadas de Pachuca (puedes cambiarlas)
LATITUD = "20.0205"
LONGITUD = "-98.7865"

# ============================================================
# 1. POEMA
# ============================================================
def obtener_poema():
    fallbacks = [
        ("El arte y la paciencia todo lo alcanzan.", "Anónimo"),
        ("Nada es tuyo, salvo el tiempo.", "Séneca"),
        ("Tarde o temprano, el que busca halla.", "Anónimo"),
    ]
    try:
        resp = requests.get("https://poetrydb.org/random/1", headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            data = resp.json()[0]
            texto = "\n".join([l for l in data["lines"] if l.strip()][:4])
            return texto, data["author"]
    except:
        pass
    return random.choice(fallbacks)

# ============================================================
# 2. FRASE
# ============================================================
def obtener_frase():
    fallbacks = [
        ("El éxito es la suma de pequeños esfuerzos repetidos día tras día.", "Robert Collier"),
        ("No cuentes los días; haz que los días cuenten.", "Muhammad Ali"),
        ("La vida es lo que pasa mientras estás ocupado haciendo otros planes.", "John Lennon"),
    ]
    try:
        resp = requests.get("https://zenquotes.io/api/random", headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            q = resp.json()[0]
            return q["q"], q["a"]
    except:
        pass
    return random.choice(fallbacks)

# ============================================================
# 3. NOTICIAS (scraping con Playwright)
# ============================================================
def obtener_noticias():
    secciones = [
        {"url": "https://oem.com.mx/elsoldehidalgo/local/", "icono": "📍", "nombre": "local"},
        {"url": "https://oem.com.mx/elsoldehidalgo/turismo/", "icono": "🎉", "nombre": "turismo"}
    ]
    todas = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        
        for sec in secciones:
            try:
                page.goto(sec["url"], timeout=20000)
                page.wait_for_selector("article a", timeout=10000)
                elementos = page.query_selector_all("article a")
                count = 0
                for el in elementos:
                    titulo = el.inner_text().strip()
                    href = el.get_attribute("href")
                    if titulo and href and len(titulo) > 10 and count < NOTICIAS_MAX:
                        url_completa = href if href.startswith("http") else f"https://oem.com.mx{href}"
                        todas.append({
                            "icono": sec["icono"],
                            "titulo": titulo,
                            "url": url_completa,
                            "seccion": sec["nombre"]
                        })
                        count += 1
            except Exception as e:
                print(f"Error en {sec['nombre']}: {e}")
        browser.close()
    
    if not todas:
        return "• No se pudieron obtener noticias hoy."
    
    resultado = ""
    for n in todas[:NOTICIAS_MAX]:
        resultado += f"{n['icono']} *{n['titulo']}*\n🔗 {n['url']}\n\n"
    return resultado

# ============================================================
# 4. CLIMA (basado en tu código de Apps Script)
# ============================================================
def obtener_clima():
    """
    Retorna un string con el resumen climático para las próximas 24 horas,
    incluyendo ventanas de lluvia con probabilidad >=38%.
    """
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={LATITUD}&lon={LONGITUD}&appid={OPENWEATHER_API_KEY}&units=metric&lang=es"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Error al obtener clima: {e}")
        return "⚠️ No se pudo obtener el pronóstico del clima."

    temp_max = -999
    temp_min = 999
    viento_max = 0
    frecuencias_desc = {}
    ventanas_lluvia = []
    
    dentro_alerta = False
    hora_inicio = ""
    hora_fin = ""
    prob_pico = 0
    
    # Procesamos los primeros 8 bloques (24 horas, cada 3 horas)
    for i in range(8):
        p = data["list"][i]
        # Convertir dt_txt a hora local CDMX
        dt_utc = datetime.strptime(p["dt_txt"], "%Y-%m-%d %H:%M:%S")
        # Ajustar a CDMX (UTC-6 estándar, UTC-5 horario verano). Usamos pytz? 
        # Para evitar dependencias extra, calculamos offset manual según fecha (simplificado: usamos UTC-6 siempre)
        # En el mensaje no es crítica la precisión del cambio de hora; el usuario entiende hora aproximada.
        # Pero para que sea exacto, usaremos la función con timezone de Python (requiere pip install pytz).
        # Alternativa: restar 6 horas directamente (CDMX sin horario verano). Es aceptable.
        hora_local = dt_utc - timedelta(hours=6)  # UTC-6 fijo (simplificado)
        hora_texto = hora_local.strftime("%I:%M %p").lstrip("0").replace(" 0", " ")
        
        # Temperaturas
        temp_max = max(temp_max, p["main"]["temp_max"])
        temp_min = min(temp_min, p["main"]["temp_min"])
        # Viento
        viento_kmh = p["wind"]["speed"] * 3.6
        viento_max = max(viento_max, viento_kmh)
        # Descripción
        desc = p["weather"][0]["description"]
        frecuencias_desc[desc] = frecuencias_desc.get(desc, 0) + 1
        # Probabilidad de lluvia (pop)
        prob_lluvia = round(p["pop"] * 100)
        
        # Detectar ventanas de lluvia >=38%
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
                ventanas_lluvia.append(f"⏳ *{hora_inicio} a {hora_fin}* | Pico máx: *{prob_pico}%* 🌧️")
                dentro_alerta = False
                prob_pico = 0
    
    if dentro_alerta:
        ventanas_lluvia.append(f"⏳ *{hora_inicio} en adelante* | Pico máx: *{prob_pico}%* 🌧️")
    
    # Descripción predominante
    desc_predominante = max(frecuencias_desc, key=frecuencias_desc.get) if frecuencias_desc else "despejado"
    desc_predominante = desc_predominante.capitalize()
    
    # Construir mensaje del clima
    clima_msg = f"⚡ *ASISTENTE CLIMÁTICO CENTRAL* ⚡\n"
    clima_msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    clima_msg += f"📊 *RESUMEN GENERAL (24 HORAS):*\n"
    clima_msg += f"🌤 *Cielo:* {desc_predominante}\n"
    clima_msg += f"🌡️ *Extremos:* {round(temp_min)}°C a {round(temp_max)}°C\n"
    clima_msg += f"💨 *Ráfagas de viento:* {round(viento_max)} km/h\n\n"
    clima_msg += f"🚨 *VENTANAS DE ATENCIÓN POR LLUVIAS:* 🚨\n"
    clima_msg += f"━━━━━━━━━━━━━━━━━━━━\n"
    
    if ventanas_lluvia:
        clima_msg += f"_Rangos críticos detectados (>38% de probabilidad):_\n\n"
        clima_msg += "\n".join(ventanas_lluvia) + "\n\n"
        clima_msg += f"⚠️ *Recomendación:* Organiza tus actividades al exterior fuera de estos horarios."
    else:
        clima_msg += f"🟢 *Todo en orden:* La probabilidad de lluvia se mantendrá baja (<38%) las próximas 24 horas. ¡Excelente día! 😎"
    
    return clima_msg

# ============================================================
# 5. CHISTE
# ============================================================
def obtener_chiste():
    try:
        resp = requests.get("https://v2.jokeapi.dev/joke/Any?lang=es&type=single&blacklistFlags=nsfw,racist,sexist")
        if resp.status_code == 200:
            data = resp.json()
            if not data.get("error") and data.get("joke"):
                return data["joke"]
    except:
        pass
    return "Programar es 10% escribir código y 90% entender por qué no funciona. 💻"

# ============================================================
# 6. CONSTRUIR MENSAJE COMPLETO (integrando clima)
# ============================================================
def construir_mensaje(poema_texto, poema_autor, frase_texto, frase_autor, noticias_texto, clima_texto, chiste_texto):
    hoy = datetime.now().strftime("%A %d de %B")
    SEP = "━━━━━━━━━━━━━━━━━━━━"
    return f"""🌅 *Buenos días — {hoy}*
{SEP}

🌹 *VERSOS DEL DÍA*
_{poema_texto}_
    ✍️ _— {poema_autor}_

🧠 *REFLEXIÓN PARA MEDITAR*
"{frase_texto}"
    ✍️ _— {frase_autor}_

{SEP}
📰 *NOTICIAS DE HIDALGO*

{noticias_texto}
{SEP}
{clima_texto}

{SEP}
😄 *MOMENTO DE RELAX*
_{chiste_texto}_

{SEP}
✨ _Un día a la vez. ¡Que tengas un gran día!_"""

# ============================================================
# 7. ENVIAR WHATSAPP
# ============================================================
def enviar_whatsapp(mensaje):
    # Limitar longitud (CallMeBot tiene límite ~4096 caracteres, pero enviaremos igual)
    # Opcional: partir mensajes muy largos.
    url = f"https://api.callmebot.com/whatsapp.php?phone={TELEFONO}&apikey={CALLMEBOT_API_KEY}&text={mensaje}"
    try:
        # CallMeBot requiere que el texto esté codificado como parámetro GET, pero requests lo hace automáticamente.
        resp = requests.get(url)
        print(f"CallMeBot respondió: {resp.status_code} - {resp.text[:100]}")
    except Exception as e:
        print(f"Error al enviar WhatsApp: {e}")

# ============================================================
# 8. FUNCIÓN PRINCIPAL
# ============================================================
def main():
    print("Obteniendo poema...")
    poema_texto, poema_autor = obtener_poema()
    print("Obteniendo frase...")
    frase_texto, frase_autor = obtener_frase()
    print("Obteniendo noticias (puede tomar unos segundos)...")
    noticias_texto = obtener_noticias()
    print("Obteniendo clima...")
    clima_texto = obtener_clima()
    print("Obteniendo chiste...")
    chiste_texto = obtener_chiste()
    
    mensaje = construir_mensaje(poema_texto, poema_autor, frase_texto, frase_autor, noticias_texto, clima_texto, chiste_texto)
    
    # Guardar copia de respaldo
    with open("mensaje.log", "w", encoding="utf-8") as f:
        f.write(mensaje)
    
    print("Enviando WhatsApp...")
    enviar_whatsapp(mensaje)
    print("¡Proceso completado!")

if __name__ == "__main__":
    main()
