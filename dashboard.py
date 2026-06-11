import requests
import json
import random
import time
import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
import os
from deep_translator import GoogleTranslator

# ============================================================
# CONFIGURACIÓN (variables de entorno)
# ============================================================
CALLMEBOT_API_KEY = os.environ.get("CALLMEBOT_API_KEY")
TELEFONO = os.environ.get("TELEFONO")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
NOTICIAS_MAX = 10  # ¡Ahora son 10 noticias por sección!

# Coordenadas de Pachuca
LATITUD = "20.0205"
LONGITUD = "-98.7865"

# Traductor
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
            if len(texto_original) > 10:
                texto_traducido = translator.translate(texto_original)
            else:
                texto_traducido = texto_original
            autor = data["author"]
            return texto_traducido, autor
    except Exception as e:
        print(f"Error en poema: {e}")
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
            texto_original = q["q"]
            autor = q["a"]
            texto_traducido = translator.translate(texto_original)
            return texto_traducido, autor
    except Exception as e:
        print(f"Error en frase: {e}")
    return random.choice(fallbacks)

# ============================================================
# 3. NOTICIAS (NUEVA VERSIÓN - solo títulos, sin URLs, más noticias)
# ============================================================
def obtener_noticias():
    secciones = [
        {"url": "https://oem.com.mx/elsoldehidalgo/local/", "icono": "📍", "nombre": "Local"},
        {"url": "https://oem.com.mx/elsoldehidalgo/turismo/", "icono": "🎉", "nombre": "Turismo"}
    ]
    todas_las_noticias = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        
        for sec in secciones:
            try:
                print(f"Accediendo a {sec['url']}...")
                page.goto(sec["url"], timeout=20000)
                page.wait_for_load_state("networkidle")
                
                # --- NUEVO MÉTODO: Extraer todo el texto de la página ---
                texto_completo = page.locator('body').inner_text()
                lineas = texto_completo.split('\n')
                
                # --- Extraer títulos: líneas que comienzan con '### ' ---
                titulos_encontrados = []
                for linea in lineas:
                    linea = linea.strip()
                    if linea.startswith('### '):
                        # Limpiar el título: eliminar '### ' y lo que sigue a 'GOSSIP'
                        titulo_limpio = linea[4:]  # Eliminar '### '
                        # Si el título contiene 'GOSSIP', cortar ahí
                        if 'GOSSIP' in titulo_limpio:
                            titulo_limpio = titulo_limpio.split('GOSSIP')[0].strip()
                        # También eliminar cualquier texto después de '### ' que no sea parte del título
                        if titulo_limpio and not titulo_limpio.startswith('¿Qué') and len(titulo_limpio) > 10:
                            titulos_encontrados.append(titulo_limpio)
                
                # Tomar los primeros NOTICIAS_MAX títulos únicos (evitar duplicados)
                titulos_unicos = []
                for t in titulos_encontrados:
                    if t not in titulos_unicos:
                        titulos_unicos.append(t)
                
                # Limitar a NOTICIAS_MAX
                titulos_final = titulos_unicos[:NOTICIAS_MAX]
                
                print(f"Se encontraron {len(titulos_final)} noticias en la sección {sec['nombre']}")
                
                # Agregar a la lista general
                for titulo in titulos_final:
                    todas_las_noticias.append({
                        "icono": sec["icono"],
                        "titulo": titulo,
                        "seccion": sec["nombre"]
                    })
                    
            except Exception as e:
                print(f"Error procesando {sec['nombre']}: {e}")
        browser.close()
    
    # Construir el texto final
    if not todas_las_noticias:
        return "• No se pudieron obtener noticias hoy."
    
    # Separar por secciones para mejor organización
    resultado = ""
    for seccion in ["Local", "Turismo"]:
        noticias_seccion = [n for n in todas_las_noticias if n["seccion"] == seccion]
        if noticias_seccion:
            resultado += f"*{seccion}*\n"
            for n in noticias_seccion:
                resultado += f"{n['icono']} {n['titulo']}\n"
            resultado += "\n"
    
    return resultado

# ============================================================
# 4. CLIMA (sin cambios)
# ============================================================
def obtener_clima():
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
                ventanas_lluvia.append(f"⏳ *{hora_inicio} a {hora_fin}* | Pico máx: *{prob_pico}%* 🌧️")
                dentro_alerta = False
                prob_pico = 0
    
    if dentro_alerta:
        ventanas_lluvia.append(f"⏳ *{hora_inicio} en adelante* | Pico máx: *{prob_pico}%* 🌧️")
    
    desc_predominante = max(frecuencias_desc, key=frecuencias_desc.get) if frecuencias_desc else "despejado"
    desc_predominante = desc_predominante.capitalize()
    
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
# 5. CHISTE (sin cambios)
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
# 6. CONSTRUIR MENSAJE (sin cambios)
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
# 7. ENVIAR WHATSAPP (sin cambios)
# ============================================================
def enviar_whatsapp(mensaje):
    import urllib.parse
    texto_codificado = urllib.parse.quote(mensaje)
    url = f"https://api.callmebot.com/whatsapp.php?phone={TELEFONO}&apikey={CALLMEBOT_API_KEY}&text={texto_codificado}"
    try:
        resp = requests.get(url)
        print(f"CallMeBot respondió: {resp.status_code} - {resp.text[:100]}")
    except Exception as e:
        print(f"Error al enviar WhatsApp: {e}")

# ============================================================
# 8. DIVIDIR MENSAJE (sin cambios)
# ============================================================
def dividir_mensaje(texto, limite=1000):
    partes = []
    while len(texto) > limite:
        corte = texto.rfind('\n', 0, limite)
        if corte == -1:
            corte = texto.rfind(' ', 0, limite)
        if corte == -1 or corte < limite - 100:
            corte = limite
        partes.append(texto[:corte].strip())
        texto = texto[corte:].strip()
    partes.append(texto)
    return partes

# ============================================================
# 9. FUNCIÓN PRINCIPAL MODIFICADA
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
    
    mensaje_completo = construir_mensaje(poema_texto, poema_autor, frase_texto, frase_autor, noticias_texto, clima_texto, chiste_texto)
    
    # Guardar copia de respaldo
    with open("mensaje.log", "w", encoding="utf-8") as f:
        f.write(mensaje_completo)
    
    # Dividir el mensaje en partes
    partes = dividir_mensaje(mensaje_completo, limite=1000)
    print(f"El mensaje se dividió en {len(partes)} parte(s).")
    
    # Enviar cada parte
    for i, parte in enumerate(partes):
        print(f"Enviando parte {i+1}/{len(partes)}...")
        enviar_whatsapp(parte)
        if i < len(partes) - 1:
            time.sleep(3)
    
    print("¡Proceso completado!")

if __name__ == "__main__":
    main()
