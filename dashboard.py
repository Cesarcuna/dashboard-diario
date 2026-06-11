import requests
import json
import random
import time
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

translator = GoogleTranslator(source='en', target='es')

# ============================================================
# 1. POEMA (traducido)
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
            texto_original = "\n".join([l for l in data["lines"] if l.strip()][:4])
            texto_traducido = translator.translate(texto_original) if len(texto_original) > 10 else texto_original
            return texto_traducido, data["author"]
    except:
        pass
    return random.choice(fallbacks)

# ============================================================
# 2. FRASE (traducida)
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
            texto_traducido = translator.translate(q["q"])
            return texto_traducido, q["a"]
    except:
        pass
    return random.choice(fallbacks)

# ============================================================
# 3. NOTICIAS (mejorado y separado por secciones)
# ============================================================
def obtener_noticias_por_seccion(url, icono, nombre):
    """Extrae títulos de noticias de una URL dada usando selectores múltiples."""
    titulos = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        try:
            page.goto(url, timeout=20000)
            page.wait_for_load_state("networkidle")
            
            # Probar múltiples selectores comunes en oem.com.mx
            selectores = [
                "article a",           # original
                "h2 a",                # títulos dentro de h2
                ".article-title a",
                ".story-title a",
                "a.story-link"
            ]
            elementos = []
            for selector in selectores:
                elementos = page.query_selector_all(selector)
                if elementos:
                    print(f"Selector '{selector}' funcionó para {nombre}")
                    break
            
            for el in elementos:
                titulo = el.inner_text().strip()
                if titulo and len(titulo) > 10 and len(titulos) < NOTICIAS_MAX:
                    # Limpiar títulos que contengan 'GOSSIP' o basura
                    if 'GOSSIP' not in titulo and 'PUBLICIDAD' not in titulo:
                        titulos.append(titulo)
        except Exception as e:
            print(f"Error en {nombre}: {e}")
        finally:
            browser.close()
    return titulos

def obtener_todas_noticias():
    secciones = [
        {"url": "https://oem.com.mx/elsoldehidalgo/local/", "icono": "📍", "nombre": "Local"},
        {"url": "https://oem.com.mx/elsoldehidalgo/turismo/", "icono": "🎉", "nombre": "Turismo"}
    ]
    noticias_por_seccion = {}
    for sec in secciones:
        print(f"Obteniendo {sec['nombre']}...")
        titulos = obtener_noticias_por_seccion(sec["url"], sec["icono"], sec["nombre"])
        noticias_por_seccion[sec["nombre"]] = titulos
        print(f"Se encontraron {len(titulos)} noticias en {sec['nombre']}")
    return noticias_por_seccion

# ============================================================
# 4. CLIMA (sin cambios, funciona)
# ============================================================
def obtener_clima():
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={LATITUD}&lon={LONGITUD}&appid={OPENWEATHER_API_KEY}&units=metric&lang=es"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Error clima: {e}")
        return "⚠️ No se pudo obtener el pronóstico."

    temp_max = -999
    temp_min = 999
    viento_max = 0
    frecuencias_desc = {}
    ventanas_lluvia = []
    dentro_alerta = False
    hora_inicio = ""
    hora_fin = ""
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
                ventanas_lluvia.append(f"⏳ {hora_inicio} a {hora_fin} | Pico máx: {prob_pico}% 🌧️")
                dentro_alerta = False
                prob_pico = 0
    
    if dentro_alerta:
        ventanas_lluvia.append(f"⏳ {hora_inicio} en adelante | Pico máx: {prob_pico}% 🌧️")
    
    desc_predominante = max(frecuencias_desc, key=frecuencias_desc.get) if frecuencias_desc else "despejado"
    desc_predominante = desc_predominante.capitalize()
    
    clima_msg = f"⚡ CLIMA HOY ⚡\n━━━━━━━━━━━━━━━━━━━━\n"
    clima_msg += f"🌡️ {round(temp_min)}°C a {round(temp_max)}°C\n"
    clima_msg += f"🌤️ {desc_predominante}\n"
    clima_msg += f"💨 Viento: {round(viento_max)} km/h\n"
    
    if ventanas_lluvia:
        clima_msg += "\n🚨 Lluvias (>38%):\n" + "\n".join(ventanas_lluvia)
    else:
        clima_msg += "\n🟢 Sin lluvias relevantes."
    
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
# 6. CONSTRUIR MENSAJES CORTOS (uno por bloque)
# ============================================================
def mensaje_bienvenida():
    hoy = datetime.now().strftime("%A %d de %B")
    return f"🌅 *Buenos días — {hoy}*\n━━━━━━━━━━━━━━━━━━━━"

def mensaje_poema_frase(poema_texto, poema_autor, frase_texto, frase_autor):
    return f"""🌹 *VERSOS DEL DÍA*
_{poema_texto}_
    ✍️ _— {poema_autor}_

🧠 *REFLEXIÓN*
"{frase_texto}"
    ✍️ _— {frase_autor}_"""

def mensaje_noticias_seccion(nombre, icono, titulos):
    if not titulos:
        return f"{icono} *{nombre}*: No hay noticias recientes."
    texto = f"{icono} *{nombre}*\n"
    for t in titulos[:NOTICIAS_MAX]:
        texto += f"• {t}\n"
    return texto

def mensaje_despedida():
    return "✨ _Un día a la vez. ¡Que tengas un gran día!_"

# ============================================================
# 7. ENVIAR WHATSAPP (un mensaje corto)
# ============================================================
def enviar_whatsapp(mensaje):
    import urllib.parse
    if not mensaje.strip():
        return
    texto_codificado = urllib.parse.quote(mensaje)
    url = f"https://api.callmebot.com/whatsapp.php?phone={TELEFONO}&apikey={CALLMEBOT_API_KEY}&text={texto_codificado}"
    try:
        resp = requests.get(url)
        print(f"Enviado ({len(mensaje)} chars) → {resp.status_code}")
        time.sleep(2)  # pequeña pausa entre mensajes
    except Exception as e:
        print(f"Error: {e}")

# ============================================================
# 8. MAIN (envío secuencial)
# ============================================================
def main():
    print("Obteniendo poema y frase...")
    poema_texto, poema_autor = obtener_poema()
    frase_texto, frase_autor = obtener_frase()
    
    print("Obteniendo noticias...")
    todas_noticias = obtener_todas_noticias()
    
    print("Obteniendo clima...")
    clima_texto = obtener_clima()
    
    print("Obteniendo chiste...")
    chiste_texto = obtener_chiste()
    
    # Enviar mensaje de bienvenida
    enviar_whatsapp(mensaje_bienvenida())
    
    # Enviar poema + frase
    enviar_whatsapp(mensaje_poema_frase(poema_texto, poema_autor, frase_texto, frase_autor))
    
    # Enviar noticias por separado (Local y Turismo)
    for nombre in ["Local", "Turismo"]:
        titulos = todas_noticias.get(nombre, [])
        icono = "📍" if nombre == "Local" else "🎉"
        msg = mensaje_noticias_seccion(nombre, icono, titulos)
        enviar_whatsapp(msg)
    
    # Enviar clima
    enviar_whatsapp(clima_texto)
    
    # Enviar chiste
    enviar_whatsapp(chiste_texto)
    
    # Enviar despedida
    enviar_whatsapp(mensaje_despedida())
    
    print("¡Dashboard completo enviado!")

if __name__ == "__main__":
    main()
