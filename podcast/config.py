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
MINUTO_MINIMO = 15        # no empieza antes de las 7:15 (El País Exprés aún puede ser el de ayer)
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
REPARTO = {"distinto": 170}   # palabras del momento Distinto Básico (va aparte, después de las noticias)
# palabras por noticia de cada bloque: con 7 titulares, 3 locales y 3 de interés salen unos 12 minutos
PALABRAS_POR_NOTICIA = {"titulares": 140, "local": 110, "interes": 150}
# «low» = el guionista piensa menos y tarda la mitad, pero se queda corto de longitud; vacío = lo normal
GUION_PENSAR = os.environ.get("GUION_PENSAR") or ""
PLAN_ESPERA_MAX = 420        # segundos desde el inicio que se espera como mucho la propuesta del Distinto Básico
LOCAL_MAX = 3                # noticias de Coruña y Galicia que entran
# Pruebas (PRUEBA=si): el resultado va a la subcarpeta «Pruebas» de Dropbox y, además, se usan
# otros modelos de Gemini. El cupo diario gratuito es pequeño y se renueva a medianoche de
# California (las 9:00 en Madrid), así que una prueba hecha durante el día sale del cupo del
# episodio de la mañana siguiente: el 14-oct-2026 las pruebas del día anterior dejaron a una de
# las voces sin el modelo principal. En prueba nunca se tocan los modelos principales, salvo
# que se pidan a propósito con MODELOS_VOZ, MODELOS_TEXTO o MODELOS_PLANES.
PRUEBA = (os.environ.get("PRUEBA") or "").lower() in ("si", "sí", "true", "1")

# Momento Distinto Básico: modelos que leen las agendas (herramienta url_context, gratuita)
MODELOS_PLANES = [m.strip() for m in (os.environ.get("MODELOS_PLANES") or (
    "gemini-3.6-flash,gemini-3-flash-preview" if PRUEBA else
    "gemini-3.8-flash,gemini-3.6-flash,gemini-3-flash-preview")).split(",") if m.strip()]
TEXTO_MAX_NOTICIA = 1800     # caracteres de cada noticia que se le pasan al guionista

MODELOS_TEXTO = [m.strip() for m in (os.environ.get("MODELOS_TEXTO") or (
    "gemini-3.6-flash,gemini-3-flash-preview,gemini-3.5-flash-lite,gemini-3.1-flash-lite" if PRUEBA else
    "gemini-3.8-flash,gemini-3.6-flash,gemini-3-flash-preview,gemini-3.5-flash-lite,gemini-3.1-flash-lite"
)).split(",") if m.strip()]

# ---------------------------------------------------------------- voces
# Dos presentadores que conversan (estilo NotebookLM). A abre el programa.
# «piper» es la voz de último recurso, sin conexión (modelo[:hablante]).
LOCUTORES = {
    "A": {
        "nombre": os.environ.get("NOMBRE_A") or "Lucía",
        "gemini": os.environ.get("VOZ_A") or "Kore",
        "edge": os.environ.get("EDGE_A") or "es-ES-ElviraNeural",
        "piper": os.environ.get("PIPER_A") or "es_ES-sharvard-medium:F",
    },
    "B": {
        "nombre": os.environ.get("NOMBRE_B") or "Martín",
        "gemini": os.environ.get("VOZ_B") or "Algieba",  # voz grave elegida por Iago el 15-oct-2026 (antes Puck)
        "edge": os.environ.get("EDGE_B") or "es-ES-AlvaroNeural",
        "piper": os.environ.get("PIPER_B") or "es_ES-davefx-medium",
    },
}
# Cómo tienen que sonar (va como «estilo» en cada turno; Google recomienda que sea corto:
# las instrucciones largas hacen que la voz se desvíe)
ESTILO_VOZ = os.environ.get("ESTILO_VOZ") or (
    "charla desenfadada entre amigos, español de España, natural, ágil y muy clara")

# Orden de intentos para la voz de Gemini: (forma de llamarla, modelo).
# OJO: en el plan gratuito cada modelo de voz admite 10 peticiones al día (el cupo se renueva a
# medianoche de California, las 9:00 en Madrid; el aviso de error de Google dice otra hora, pero
# no es la real). Un episodio gasta 4 (2 tandas por voz). Si el modelo principal se queda sin cupo
# a mitad de una voz, esa voz entera se rehace con el siguiente, para que no cambie de timbre.
_MODELOS_VOZ_DEFECTO = ("interactions:gemini-3.8-flash-lite-tts,generate:gemini-3.1-flash-tts-preview,"
                        "generate:gemini-2.5-flash-preview-tts" if PRUEBA else
                        "interactions:gemini-3.8-flash-tts,interactions:gemini-3.8-flash-lite-tts,"
                        "generate:gemini-3.1-flash-tts-preview,generate:gemini-2.5-flash-preview-tts")
MODELOS_VOZ = [tuple(x.strip().split(":", 1)) for x in
               (os.environ.get("MODELOS_VOZ") or _MODELOS_VOZ_DEFECTO).split(",") if ":" in x]
VOZ_MAX_CARACTERES = int(os.environ.get("VOZ_MAX_CARACTERES") or 3800)   # unas 4 tandas por episodio
WHISPER_MODELO = os.environ.get("WHISPER_MODELO") or "small"  # transcripción para cortar los turnos («base» reconocía peor las palabras sueltas)
VOZ_PAUSA_ENTRE_TURNOS = True   # etiqueta <long pause> de Gemini 3.8 entre turnos de una misma voz
VOZ_TIMEOUT = 180            # segundos de espera máxima por petición de voz (si no, otro modelo)
EDGE_VELOCIDAD = "+4%"
PIPER_LENTITUD = 0.95        # <1 = algo más rápido
# Motor de voz: "gemini" (con reservas automáticas: Edge y, si no, Piper), "edge" o "piper"
MOTOR_VOZ = (os.environ.get("MOTOR_VOZ") or "gemini").strip().lower()

# ---------------------------------------------------------------- Dropbox (carpeta de la app)
# En las pruebas (PRUEBA=si) todo va a la subcarpeta «Pruebas», para no pisar el episodio del día
_PREFIJO = "/Pruebas" if PRUEBA else ""
DROPBOX_MP3 = _PREFIJO + "/Noticiario de hoy.mp3"
DROPBOX_GUION = _PREFIJO + "/Guion de hoy.md"
DROPBOX_PLANES_CRITERIOS = "/Distinto Básico.txt"              # criterios de Iago (solo en Dropbox)
DROPBOX_PLANES_HISTORIAL = "/Distinto Básico - propuestas.txt"  # lo ya propuesto, para no repetir
DROPBOX_CUMPLES = "/Cumpleaños.txt"   # la lista de cumpleaños vive SOLO aquí (el repositorio es público)
DROPBOX_MUSICA = "/musica"   # intro / transicion / cierre (.mp3 o .wav); si no hay, va sin música
DROPBOX_DIAGNOSTICO = _PREFIJO + "/Diagnóstico.txt"   # datos técnicos de la última ejecución
# lotes de voz tal cual salen de Gemini, con sus textos y cortes (se sobrescriben en cada ejecución)
DROPBOX_CRUDO = "/Pruebas/Crudo de la prueba" if PRUEBA else "/Pruebas/Crudo del episodio"

# ---------------------------------------------------------------- montaje
MP3_KBPS = "96k"
SONORIDAD_LUFS = -16          # nivel estándar de pódcast
