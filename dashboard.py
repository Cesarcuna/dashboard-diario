import requests
import re
import random
import time
from datetime import datetime, timedelta
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
# 1. POEMA
# ============================================================
def obtener_poema():
    fallbacks = [
        ("El arte y la paciencia todo lo alcanzan.", "Anónimo"),
        ("Nada es tuyo, salvo el tiempo.", "Séneca"),
        ("Tarde o temprano, el que busca halla.", "Anónimo"),
    ]
    try:
        resp = requests.get("https://poetrydb.org/random/1", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()[0]
            texto_original = "\n".join([l for l in data["lines"] if l.strip()][:4])
            texto_traducido = translator.translate(texto_original) if len(texto_original) > 10 else texto_original
            return texto_traducido, data["author"]
    except Exception as e:
        print(f"Error poema: {e}")
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
        resp = requests.get("https://zenquotes.io/api/random", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code == 200:
            q = resp.json()[0]
            texto_traducido = translator.translate(q["q"])
            return texto_traducido, q["a"]
    except Exception as e:
        print(f"Error frase: {e}")
    return random.choice(fallbacks)

# ============================================================
# 3. NOTICIAS (usando regex, sin Playwright)
# ============================================================
def extraer_titulos_de_url(url, patron_exclusion=None):
    """Obtiene títulos de noticias desde el HTML de una URL."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text
        
        # Buscar patrones de títulos en etiquetas <a> que contengan URLs del sitio
        # Ejemplo: <a href="/elsoldehidalgo/local/...">Título</a>
        patron = r'<a[^>]+href="[^"]*?(?:elsoldehidalgo/(?:local|turismo)/[^"]+)"[^>]*>([^<]+)</a>'
        matches = re.findall(patron, html)
        
        # Limpiar y filtrar títulos
        titulos = []
        for m in matches:
            titulo = m.strip()
            if titulo and len(titulo) > 10 and not titulo.startswith('LEER'):
                # Evitar basura como "GOSSIP" o "PUBLICIDAD"
                if 'GOSSIP' not in titulo and 'PUBLICIDAD' not in titulo:
                    titulos.append(titulo)
        
        # Eliminar duplicados (algunos enlaces se repiten)
        titulos_unicos = []
        for t in titulos:
            if t not in titulos_unicos:
                titulos_unicos.append(t)
        
        return titulos_unicos[:NOTICIAS_MAX]
    except Exception as e:
        print(f"Error extrayendo de {url}: {e}")
        return []

def obtener_todas_noticias():
    secciones = {
        "Local": "https://oem.com.mx/elsoldehidalgo/local/",
        "Turismo": "https://oem.com.mx/elsoldehidalgo/turismo/"
    }
    resultados = {}
    for nombre, url in secciones.items():
        print(f"Extrayendo {nombre}...")
        titulos = extraer_titulos_de_url(url)
        resultados[nombre] = titulos
        print(f"  Encontrados {len(titulos)} títulos.")
    return resultados

# ============================================================
# 4. CLIMA (resumido)
# ============================================================
def obtener_clima():
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={LATITUD}&lon={LONGITUD}&appid={OPENWEATHER_API_KEY}&units=metric&lang=es"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"⚠️ Clima no disponible: {e}"
    
    temp_max = -999
    temp_min = 999
    viento_max = 0
    alerta_lluvia = False
    prob_max = 0
    
    for i in range(8):  # 24 horas
        p = data["list"][i]
        temp_max = max(temp_max, p["main"]["temp_max"])
        temp_min = min(temp_min, p["main"]["temp_min"])
        viento_kmh = p["wind"]["speed"] * 3.6
        viento_max = max(viento_max, viento_kmh)
        prob = round(p["pop"] * 100)
        if prob > prob_max:
            prob_max = prob
        if prob >= 38:
            alerta_lluvia = True
    
    desc = data["list"][0]["weather"][0]["description"].capitalize()
    
    clima = f"🌡️ {round(temp_min)}°C a {round(temp_max)}°C\n"
    clima += f"🌤️ {desc}\n"
    clima += f"💨 Viento: {round(viento_max)} km/h\n"
    if alerta_lluvia:
        clima += f"🌧️ Prob. lluvia: {prob_max}% (posible)"
    else:
        clima += "☀️ Sin lluvias relevantes"
    return clima

# ============================================================
# 5. CHISTE
# ============================================================
def obtener_chiste():
    try:
        resp = requests.get("https://v2.jokeapi.dev/joke/Any?lang=es&type=single&blacklistFlags=nsfw,racist,sexist", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if not data.get("error") and data.get("joke"):
                return data["joke"]
    except:
        pass
    return "Programar es 10% escribir código y 90% entender por qué no funciona. 💻"

# ============================================================
# 6. MENSAJES CORTOS
# ============================================================
def mensaje_bienvenida():
    hoy = datetime.now().strftime("%A %d de %B")
    return f"🌅 Buenos días — {hoy}"

def mensaje_poema_frase(poema, autor_poema, frase, autor_frase):
    return f"🌹 Verso:\n{poema}\n— {autor_poema}\n\n🧠 Reflexión:\n{frase}\n— {autor_frase}"

def mensaje_noticias_seccion(nombre, icono, titulos):
    if not titulos:
        return f"{icono} {nombre}: Sin noticias nuevas"
    texto = f"{icono} {nombre}\n"
    for t in titulos[:NOTICIAS_MAX]:
        texto += f"• {t}\n"
    return texto.strip()

def mensaje_despedida():
    return "✨ Un día a la vez. ¡Que tengas un gran día!"

# ============================================================
# 7. ENVIAR WHATSAPP
# ============================================================
def enviar_whatsapp(mensaje):
    if not mensaje or len(mensaje) < 5:
        return
    import urllib.parse
    texto = urllib.parse.quote(mensaje)
    url = f"https://api.callmebot.com/whatsapp.php?phone={TELEFONO}&apikey={CALLMEBOT_API_KEY}&text={texto}"
    try:
        resp = requests.get(url, timeout=15)
        print(f"Enviado ({len(mensaje)} chars) → {resp.status_code}")
        time.sleep(2)  # esperar para no saturar
    except Exception as e:
        print(f"Error enviando: {e}")

# ============================================================
# 8. MAIN
# ============================================================
def main():
    print("=== Iniciando dashboard diario ===")
    
    print("1. Poema y frase...")
    poema, autor_poema = obtener_poema()
    frase, autor_frase = obtener_frase()
    
    print("2. Noticias...")
    noticias = obtener_todas_noticias()
    
    print("3. Clima...")
    clima = obtener_clima()
    
    print("4. Chiste...")
    chiste = obtener_chiste()
    
    # Enviar bloques
    enviar_whatsapp(mensaje_bienvenida())
    time.sleep(1)
    enviar_whatsapp(mensaje_poema_frase(poema, autor_poema, frase, autor_frase))
    time.sleep(1)
    
    if "Local" in noticias:
        enviar_whatsapp(mensaje_noticias_seccion("Local", "📍", noticias["Local"]))
        time.sleep(1)
    if "Turismo" in noticias:
        enviar_whatsapp(mensaje_noticias_seccion("Turismo", "🎉", noticias["Turismo"]))
        time.sleep(1)
    
    enviar_whatsapp(f"⛅ Clima:\n{clima}")
    time.sleep(1)
    enviar_whatsapp(f"😂 Chiste:\n{chiste}")
    time.sleep(1)
    enviar_whatsapp(mensaje_despedida())
    
    print("=== Dashboard enviado correctamente ===")

if __name__ == "__main__":
    main()
