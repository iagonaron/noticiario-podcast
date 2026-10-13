"""Momento Distinto Básico: una propuesta de plan distinta cada día para Iago y Laura.

Gemini lee las agendas de A Coruña de hoy y de los próximos días (herramienta «url_context», que
sí entra en el plan gratuito; la búsqueda de Google no) y elige un plan siguiendo los criterios
que Iago tiene en su Distinto Básico. Los criterios viven SOLO en su Dropbox privado
(«Distinto Básico.txt» en la carpeta del pódcast), nunca en este repositorio público, y lo ya
propuesto se apunta en «Distinto Básico - propuestas.txt» para no repetir.
"""
import datetime as dt
import json
import os
import re
import time

import requests

from . import config, util

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
PROHIBIDO = re.compile(r"acuario|aquarium|zoo\b|zool[oó]gico|delf[ií]n|granja[- ]escuela|circo con animales|"
                       r"doma|rodeo|corrida|tauri", re.I)


MESES_URL = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
             "octubre", "noviembre", "diciembre"]


def fuentes_del_dia(hoy):
    """Agendas que se le dan a leer: la del Concello, la de Quincemil de varios días (rotando),
    los conciertos del mes y un agregador de planes."""
    urls = ["https://www.coruna.gal/cultura/es/agenda/proximos-eventos"]
    desfase = hoy.toordinal() % 2          # un día pares, otro impares: más variedad
    for d in (desfase, 2 + desfase, 4 + desfase, 6 + desfase):
        f = hoy + dt.timedelta(days=d)
        urls.append(f"https://www.elespanol.com/quincemil/servicios/agenda/dia/{f.day}-{f.month}-{f.year}")
    meses = {hoy.month: hoy.year}
    luego = hoy + dt.timedelta(days=9)
    meses[luego.month] = luego.year
    for mes, anio in meses.items():
        urls.append(f"https://www.laganzua.net/conciertos/coruna/{MESES_URL[mes - 1]}-{anio}")
    urls.append("https://planomato.com/es/a-coruna")
    return urls


def _texto_respuesta(j):
    partes = (((j.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
    return "".join(p.get("text", "") for p in partes if not p.get("thought")).strip()


def _leidas(j):
    """Qué páginas pudo leer de verdad (metadatos de url_context): [(url, estado)]."""
    c = (j.get("candidates") or [{}])[0]
    meta = c.get("urlContextMetadata") or c.get("url_context_metadata") or {}
    salida = []
    for u in meta.get("urlMetadata") or meta.get("url_metadata") or []:
        salida.append((u.get("retrievedUrl") or u.get("retrieved_url") or "?",
                       (u.get("urlRetrievalStatus") or u.get("url_retrieval_status") or "?").replace("URL_RETRIEVAL_STATUS_", "")))
    return salida


def _json_de(texto):
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        raise ValueError("la respuesta no trae JSON")
    return json.loads(m.group(0))


def _pregunta(hoy, criterios, historial, urls):
    fecha = util.fecha_larga(dt.datetime.combine(hoy, dt.time(8)))
    desde, hasta = hoy + dt.timedelta(days=2), hoy + dt.timedelta(days=9)
    ya = "\n".join(f"- {l}" for l in historial[-25:]) or "- (ninguno todavía)"
    agendas = "\n".join(urls)
    return f"""Hoy es {fecha} de {hoy.year}. Lee estas agendas de A Coruña y alrededores:
{agendas}

y elige UNA propuesta de plan para hoy o para los próximos días, siguiendo estos criterios de Iago para su «Distinto Básico» (planes en pareja con Laura):

{criterios}

YA PROPUESTOS (no repitas ninguno; si puedes, tampoco el mismo sitio de comida):
{ya}

CÓMO ELEGIR
- Varía de un día para otro: unos días algo con fecha entre el {util.fecha_larga(dt.datetime.combine(desde, dt.time(8)))} y el {util.fecha_larga(dt.datetime.combine(hasta, dt.time(8)))} para lo que convenga sacar entradas o reservar con unos días de antelación; otros, algo de esta misma semana o de hoy que se pueda hacer sin organizar casi nada.
- Usa SOLO lo que digan esas páginas para la fecha, la hora, el lugar, el precio y si hay que reservar. Si un dato no viene, pon null: no lo inventes. Antes algo sencillo y seguro que algo dudoso.
- Para comer: de la lista de sitios de los criterios, el que esté más cerca del lugar de la actividad (si no sabes cuál, uno céntrico); di qué tiene vegano según la lista.

Responde SOLO con un objeto JSON, sin texto antes ni después, con estas claves:
{{"titulo": "nombre del plan",
 "que_es": "dos o tres frases: qué es, quién lo organiza y qué te encuentras",
 "por_que": "una frase: por qué les puede gustar a Iago y a Laura",
 "dia": "AAAA-MM-DD, o null si se puede hacer cualquier día de esta semana",
 "hora": "HH:MM, o null",
 "cuando": "cómo se diría en voz alta, p. ej. «el jueves dieciséis a las ocho y media de la tarde»",
 "lugar": "sitio y barrio o municipio",
 "precio": "precio para los dos, o «gratis»",
 "reserva": "si hay que reservar o sacar entradas: dónde y con cuánta antelación; si no, «no hace falta»",
 "comer": {{"nombre": "...", "donde": "dirección o zona", "que": "qué tienen vegano"}},
 "visma": "true si puede ir la perra, false si no",
 "fuente": "URL donde se confirma"}}"""


def _valido(p, hoy, historial):
    if not isinstance(p, dict) or not str(p.get("titulo") or "").strip() or not str(p.get("que_es") or "").strip():
        return "faltan el título o la descripción"
    todo = " ".join(str(v) for v in p.values() if isinstance(v, (str, int, float)))
    if PROHIBIDO.search(todo):
        return "tiene animales cautivos"
    if p.get("dia"):
        try:
            d = dt.date.fromisoformat(str(p["dia"])[:10])
        except ValueError:
            return f"fecha rara: {p['dia']}"
        if not hoy <= d <= hoy + dt.timedelta(days=14):
            return f"fecha fuera de plazo: {d}"
    titulo = util.sin_tildes(str(p["titulo"]).lower())
    for linea in historial[-40:]:
        if titulo[:40] and titulo[:40] in util.sin_tildes(linea.lower()):
            return "repetido"
    return None


def proponer(hoy, criterios, historial):
    """Devuelve (plan o None, avisos). El plan es un diccionario listo para el guionista."""
    avisos = []
    if not criterios or not os.environ.get("GEMINI_API_KEY"):
        return None, ["Distinto Básico: faltan los criterios o la clave de Gemini"]
    urls = fuentes_del_dia(hoy)
    pregunta = _pregunta(hoy, criterios, historial, urls)
    for modelo in config.MODELOS_PLANES:
        for intento in range(2):
            t0 = time.time()
            try:
                r = requests.post(URL.format(modelo=modelo), timeout=180,
                                  headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
                                  json={"contents": [{"role": "user", "parts": [{"text": pregunta}]}],
                                        "tools": [{"url_context": {}}],
                                        "generationConfig": {"temperature": 0.8}})
                if r.status_code != 200:
                    m = re.search(r'"message"\s*:\s*"([^"]{0,160})', r.text)
                    raise RuntimeError(f"HTTP {r.status_code}: {m.group(1) if m else r.text[:160]}")
                j = r.json()
                plan = _json_de(_texto_respuesta(j))
                motivo = _valido(plan, hoy, historial)
                if motivo:
                    raise RuntimeError(f"propuesta descartada ({motivo})")
                leidas = _leidas(j)
                plan["fuentes"] = [u for u, est in leidas if "SUCCESS" in est.upper()]
                plan["modelo"] = modelo
                plan["lectura"] = ", ".join(f"{u.split('/')[2] if '//' in u else u}: {est.lower()}" for u, est in leidas)
                util.log(f"Distinto Básico: {modelo} en {time.time() - t0:.0f}s · páginas: {plan['lectura']}")
                return plan, avisos
            except Exception as e:
                avisos.append(f"Distinto Básico · {modelo}: {str(e)[:200]}")
                util.log(avisos[-1])
                if "HTTP 429" in str(e) or "HTTP 5" in str(e):
                    time.sleep(10)
    return None, avisos


def linea_historial(hoy, plan):
    comer = plan.get("comer") or {}
    return " · ".join(str(x) for x in (hoy.isoformat(), plan.get("titulo"), plan.get("cuando") or plan.get("dia") or "",
                                       plan.get("lugar") or "", f"comer: {comer.get('nombre', '')}",
                                       plan.get("fuente") or "") if x)
