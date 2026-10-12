"""Ajustes del pódcast. Todo lo que se puede cambiar sin tocar el resto del código está aquí.

Algunos valores se pueden cambiar también desde GitHub, sin editar este fichero:
Settings → Secrets and variables → Actions → pestaña «Variables» (VOZ_A, VOZ_B, ...).
"""
import os

# ---------------------------------------------------------------- dónde y cuándo
NOTICIARIO_URL = "https://noticiarioiago.netlify.app/"
PROXY_NETLIFY = "https://noticiarioiago.netlify.app/proxy/"   # el mismo proxy que usa el noticiario
ZONA = "Europe/Madrid"
LAT, LON = 43.3713, -8.396          # A Coruña (las mismas del noticiario)
CONCELLO = "15030"                   # código de A Coruña en MeteoGalicia y AEMET

# Ventana en la que el robot automático puede generar el episodio (hora de Madrid).
# Fuera de ella solo se genera si lo lanzas tú a mano desde GitHub.
HORA_MINIMA = 7
HORA_MAXIMA = 11

# Franjas de los paseos (horas de Madrid, la segunda cifra no incluida)
PASEOS = {
    "paseo de la mañana": (8, 10),
    "paseo de la noche": (20, 22),
}

# Umbrales del tiempo
PROB_LLUVIA_FRANJA = 40     # % a partir del cual una hora cuenta como «puede llover»
UV_PROTECCION = 3           # índice UV a partir del cual se recomienda protección solar

# ---------------------------------------------------------------- guion
PALABRAS_MIN = 1350          # sin contar la agenda
PALABRAS_MAX = 1800
TEXTO_MAX_NOTICIA = 1800     # caracteres de cada noticia que se le pasan al guionista

MODELOS_TEXTO = [m.strip() for m in os.environ.get(
    "MODELOS_TEXTO",
    "gemini-3.8-flash,gemini-3.6-flash,gemini-3-flash-preview,gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash",
).split(",") if m.strip()]

# ---------------------------------------------------------------- voces
# A abre el programa; los bloques se reparten alternando A y B.
LOCUTORES = {
    "A": {
        "nombre": os.environ.get("NOMBRE_A") or "Lucía",
        "gemini": os.environ.get("VOZ_A") or "Kore",
        "edge": os.environ.get("EDGE_A") or "es-ES-ElviraNeural",
        "estilo": ("Locutora de un informativo de radio matinal en España, acento castellano peninsular. "
                   "Tono cercano, claro y ágil; natural, sin dramatizar ni exagerar."),
    },
    "B": {
        "nombre": os.environ.get("NOMBRE_B") or "Martín",
        "gemini": os.environ.get("VOZ_B") or "Charon",
        "edge": os.environ.get("EDGE_B") or "es-ES-AlvaroNeural",
        "estilo": ("Locutor de un informativo de radio matinal en España, acento castellano peninsular. "
                   "Tono cercano, claro y ágil; natural, sin dramatizar ni exagerar."),
    },
}

# Orden de intentos para la voz de Gemini: (forma de llamarla, modelo)
MODELOS_VOZ = [
    ("interactions", "gemini-3.8-flash-tts"),
    ("interactions", "gemini-3.8-flash-lite-tts"),
    ("interactions", "gemini-3.1-flash-tts-preview"),
    ("generate", "gemini-3.1-flash-tts-preview"),
    ("generate", "gemini-2.5-flash-preview-tts"),
]
VOZ_MAX_CARACTERES = 2200    # trozos más largos se parten por párrafos
EDGE_VELOCIDAD = "+4%"
# Motor de voz: "gemini" (con reserva automática Edge) o "edge" (solo Edge)
MOTOR_VOZ = (os.environ.get("MOTOR_VOZ") or "gemini").strip().lower()

# ---------------------------------------------------------------- Dropbox (carpeta de la app)
DROPBOX_MP3 = "/Noticiario de hoy.mp3"
DROPBOX_GUION = "/Guion de hoy.md"
DROPBOX_CUMPLES = "/Cumpleaños.txt"   # la lista de cumpleaños vive SOLO aquí (el repositorio es público)
DROPBOX_MUSICA = "/musica"   # si dejas aquí intro / transicion / fondo / cierre (.mp3 o .wav), se usan esos

# ---------------------------------------------------------------- montaje
MP3_KBPS = "96k"
SONORIDAD_LUFS = -16          # nivel estándar de pódcast
