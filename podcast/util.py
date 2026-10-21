"""Utilidades comunes: hora de Madrid, descargas con reintento y formato hablado."""
import datetime as dt
import json
import re
import time
import urllib.parse
from zoneinfo import ZoneInfo

import requests

from . import config

MADRID = ZoneInfo(config.ZONA)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def ahora():
    return dt.datetime.now(MADRID)


def fecha_larga(d):
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


def log(*partes):
    print(time.strftime("%H:%M:%S"), *partes, flush=True)


def por_proxy(url):
    """La misma URL pasando por el proxy de Netlify del noticiario."""
    return config.PROXY_NETLIFY + re.sub(r"^https?://", "", url)


def descargar(url, como="text", timeout=25, intentos=2, proxy=True, encoding=None, etiqueta=None):
    """Descarga directa y, si falla, a través del proxy de Netlify del noticiario.
    Con `etiqueta`, los errores no muestran la dirección (para las direcciones secretas de los calendarios:
    el repositorio es público y sus registros también)."""
    urls = [url] + ([por_proxy(url)] if proxy else [])
    ultimo = None
    for u in urls:
        for i in range(intentos):
            try:
                r = requests.get(u, timeout=timeout, headers={"User-Agent": UA})
                if r.status_code == 200 and r.content:
                    if como == "json":
                        return json.loads(r.content.decode(encoding or "utf-8", "replace"))
                    if como == "bytes":
                        return r.content
                    return r.content.decode(encoding or r.encoding or "utf-8", "replace")
                ultimo = f"HTTP {r.status_code}"
            except Exception as e:  # red, json…
                ultimo = type(e).__name__ if etiqueta else repr(e)
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"No se pudo descargar {etiqueta or url}: {ultimo}")


# ---------------------------------------------------------------- forma hablada
def hora_hablada(h, minutos=0):
    """14 → 'las dos de la tarde'; 13 → 'la una de la tarde'; 8:45 → 'las nueve menos cuarto de la mañana'."""
    h = int(h) % 24
    m = int(minutos or 0)
    if h == 0 and m == 0:
        return "medianoche"
    if h == 12 and m == 0:
        return "las doce del mediodía"
    if m == 45:
        ref, sufijo = (h + 1) % 24, " menos cuarto"
    else:
        ref, sufijo = h, {0: "", 15: " y cuarto", 30: " y media"}.get(m, f" y {m}")
    h12 = ref % 12 or 12
    art = "la" if h12 == 1 else "las"
    num = NUMEROS.get(h12, str(h12)) + sufijo
    if h < 6:
        parte = "de la madrugada"
    elif h < 12:
        parte = "de la mañana"
    elif h < 13:
        parte = "del mediodía"
    elif h < 21:
        parte = "de la tarde"
    else:
        parte = "de la noche"
    return f"{art} {num} {parte}"


NUMEROS = {1: "una", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis", 7: "siete",
           8: "ocho", 9: "nueve", 10: "diez", 11: "once", 12: "doce"}


def lista_hablada(cosas):
    cosas = [c for c in cosas if c]
    if not cosas:
        return ""
    if len(cosas) == 1:
        return cosas[0]
    return ", ".join(cosas[:-1]) + " y " + cosas[-1]


def palabras(texto):
    return len(re.findall(r"\w+", texto or ""))


def _es_flecha(o):
    return (0x2190 <= o <= 0x21FF or 0x27A1 <= o <= 0x27BF or 0x2B00 <= o <= 0x2B11 or 0x27F0 <= o <= 0x27FF
            or 0x2900 <= o <= 0x297F or 0x1F800 <= o <= 0x1F8FF)


def sin_emojis(texto):
    """Quita emojis y pictogramas (la voz los leería raro o haría una pausa extraña). En su sitio deja
    un espacio, para no pegar palabras, y una flecha se lee «a»: «9.30➡️13.30» → «9.30 a 13.30»
    (el 21-oct-2026 la agenda decía «9.3013.30»)."""
    import unicodedata
    fuera = []
    for c in texto or "":
        o = ord(c)
        if c in "\u200d\ufe0f\ufe0e\u20e3":           # unen o matizan emojis: fuera sin más
            continue
        if _es_flecha(o) and o != 0x21B5:
            fuera.append(" a ")
        elif 0x1F000 <= o <= 0x1FAFF or 0x1F1E6 <= o <= 0x1F1FF or (o >= 0x2190 and unicodedata.category(c) in ("So", "Sk")):
            fuera.append(" ")
        else:
            fuera.append(c)
    t = re.sub(r"[ \t]{2,}", " ", "".join(fuera))
    t = re.sub(r" ([,.;:!?)])", r"\1", t)             # «hola 🎉, ¿qué tal?» → «hola, ¿qué tal?»
    t = re.sub(r"(^|[\s(])a (?=a\b)", r"\1", t)       # dos flechas seguidas: una sola «a»
    return t.strip()


def sin_tildes(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def quitar_url(texto):
    return re.sub(r"https?://\S+", "", texto or "")


def url_encode(s):
    return urllib.parse.quote(s, safe="")
