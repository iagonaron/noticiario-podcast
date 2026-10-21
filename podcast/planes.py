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
# lo más que se espera una respuesta: leer cinco agendas y pensar lleva de uno a cuatro minutos
# (el 21-oct-2026, con 150 s, dos peticiones seguidas se cortaron antes de responder)
ESPERA_PETICION = int(os.environ.get("PLAN_ESPERA_PETICION") or 240)
PROHIBIDO = re.compile(r"acuario|aquarium|zoo\b|zool[oó]gico|delf[ií]n|granja[- ]escuela|circo con animales|"
                       r"doma|rodeo|corrida|tauri", re.I)


MESES_URL = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
             "octubre", "noviembre", "diciembre"]


def fuentes_del_dia(hoy):
    """Agendas que se le dan a leer: la del Concello, la de Quincemil de varios días (rotando),
    los conciertos del mes y un agregador de planes."""
    urls = ["https://www.coruna.gal/cultura/es/agenda/proximos-eventos",
            f"https://www.elespanol.com/quincemil/servicios/agenda/dia/{hoy.day}-{hoy.month}-{hoy.year}"]
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


def _opciones(texto):
    """Las propuestas de la respuesta, en orden: {"opciones": [...]} o, si viene una sola, [esa]."""
    j = _json_de(texto)
    if isinstance(j, dict) and isinstance(j.get("opciones"), list):
        return [o for o in j["opciones"] if isinstance(o, dict)]
    return [j]


def _pregunta(hoy, criterios, historial, urls):
    fecha = util.fecha_larga(dt.datetime.combine(hoy, dt.time(8)))
    desde, hasta = hoy + dt.timedelta(days=2), hoy + dt.timedelta(days=9)
    ya = "\n".join(f"- {l}" for l in historial[-25:]) or "- (ninguno todavía)"
    agendas = "\n".join(urls)
    return f"""Hoy es {fecha} de {hoy.year}. Lee estas agendas de A Coruña y alrededores:
{agendas}

y elige TRES propuestas de plan para hoy o para los próximos días (tres eventos distintos, en sitios distintos), ordenadas de la que más te convence a la que menos, siguiendo estos criterios de Iago para su «Distinto Básico» (planes en pareja con Laura):

{criterios}

YA PROPUESTOS (no repitas ninguno: ni el mismo evento ni el mismo lugar de actividad en al menos una semana; si puedes, tampoco el mismo sitio de comida):
{ya}

CÓMO ELEGIR
- Varía de un día para otro: unos días algo con fecha entre el {util.fecha_larga(dt.datetime.combine(desde, dt.time(8)))} y el {util.fecha_larga(dt.datetime.combine(hasta, dt.time(8)))} para lo que convenga sacar entradas o reservar con unos días de antelación; otros, algo de esta misma semana o de hoy que se pueda hacer sin organizar casi nada.
- Usa SOLO lo que digan esas páginas para la fecha, la hora, el lugar, el precio y si hay que reservar. Si un dato no viene, pon null: no lo inventes. Antes algo sencillo y seguro que algo dudoso.
- Para comer: SOLO uno de la lista de sitios que viene en los criterios (copia su nombre tal cual), el que esté más cerca del lugar de la actividad; di qué tiene vegano según la lista. Nunca te inventes un sitio: si no hay lista, pon "comer": null.

Responde SOLO con un objeto JSON, sin texto antes ni después: {{"opciones": [propuesta 1, propuesta 2, propuesta 3]}}, y cada propuesta con estas claves:
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
    if p.get("hora") and not re.match(r"^\d{1,2}:\d{2}$", str(p["hora"])):
        p["hora"] = None
    if _repetido(p, historial):
        return "repetido"
    return None


def _claves(texto):
    """Palabras con contenido de un texto (sin tildes ni palabras vacías)."""
    vacias = {"de", "del", "la", "el", "los", "las", "en", "y", "a", "con", "por", "para", "un", "una", "al",
              "coruna", "concierto", "festival", "sesion", "proyeccion", "edicion", "2026", "2027",
              "internacional", "internacionales", "exposicion", "teatro", "musica", "museo", "taller", "charla",
              "noche", "visita", "ruta", "mercado", "feria", "fiesta", "jornada", "jornadas", "ciclo", "cine",
              "presentacion", "espectaculo", "danza", "obra", "directo", "vivo", "gratis", "gratuita", "gratuito",
              "programa", "galicia", "gallego", "gallega", "cortos", "cortometrajes", "peliculas", "pelicula"}
    return {w for w in re.findall(r"[a-z0-9ñ]{3,}", util.sin_tildes(texto or "").lower()) if w not in vacias}


def _repetido(p, historial):
    """¿Es el mismo plan (o el mismo sitio de actividad) que alguno de los últimos días?"""
    import difflib
    titulo = util.sin_tildes(str(p.get("titulo") or "")).lower()
    lugar = _claves(p.get("lugar"))
    for k, linea in enumerate(reversed(historial[-21:])):
        partes = [x.strip() for x in linea.split(" · ")]
        if len(partes) < 2:
            continue
        viejo = util.sin_tildes(partes[1]).lower()
        if difflib.SequenceMatcher(None, titulo, viejo).ratio() >= 0.6:
            return True
        comunes = _claves(partes[1]) & _claves(titulo)
        if len(comunes) >= 2 or any(len(w) >= 8 for w in comunes):
            return True          # mismo evento con otro título (p. ej. el mismo festival)
        if k < 7 and len(partes) >= 4 and lugar and len(lugar & _claves(partes[3])) >= max(1, min(2, len(lugar))):
            return True          # mismo sitio de actividad en la última semana
    return False


def _en_lista(nombre, criterios):
    """¿Aparece ese sitio en la lista de los criterios? (sin tildes ni mayúsculas)"""
    n = util.sin_tildes(nombre or "").lower().strip()
    n = re.sub(r"^(restaurante|bar|cafeteria|taberna)\s+", "", n)
    return len(n) >= 4 and n[:20] in util.sin_tildes(criterios or "").lower()


def proponer(hoy, criterios, historial, limite=None):
    """Devuelve (plan o None, avisos). El plan es un diccionario listo para el guionista.
    `limite`: hora (time.time()) a la que tiene que haber terminado; cada petición espera como mucho
    lo que quede (el 20-oct-2026 una petición colgada se comió 200 s y el día se quedó sin plan)."""
    avisos = []
    if not criterios or not os.environ.get("GEMINI_API_KEY"):
        return None, ["Distinto Básico: faltan los criterios o la clave de Gemini"]
    urls = fuentes_del_dia(hoy)
    pregunta = _pregunta(hoy, criterios, historial, urls)
    limite = limite or (time.time() + 330)
    for modelo in config.MODELOS_PLANES:
        for intento in range(2):
            queda = limite - time.time()
            if queda < 45:
                avisos.append("Distinto Básico: se acabó el tiempo para buscar el plan")
                return None, avisos
            t0 = time.time()
            try:
                r = requests.post(URL.format(modelo=modelo), timeout=min(ESPERA_PETICION, queda - 5),
                                  headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
                                  json={"contents": [{"role": "user", "parts": [{"text": pregunta}]}],
                                        "tools": [{"url_context": {}}],
                                        "generationConfig": {"temperature": 0.8}})
                if r.status_code != 200:
                    m = re.search(r'"message"\s*:\s*"([^"]{0,160})', r.text)
                    raise RuntimeError(f"HTTP {r.status_code}: {m.group(1) if m else r.text[:160]}")
                j = r.json()
                plan, descartes = None, []
                for opcion in _opciones(_texto_respuesta(j))[:3]:
                    motivo = _valido(opcion, hoy, historial)
                    if not motivo:
                        plan = opcion
                        break
                    descartes.append(motivo)
                if not plan:
                    raise RuntimeError(f"propuestas descartadas ({'; '.join(descartes) or 'ninguna'})")
                if descartes:
                    avisos.append(f"Distinto Básico: antes de la elegida se descartaron {len(descartes)} ({'; '.join(descartes)})")
                comer = plan.get("comer") if isinstance(plan.get("comer"), dict) else None
                if comer and not _en_lista(comer.get("nombre", ""), criterios):
                    avisos.append(f"Distinto Básico: el sitio de comer propuesto no estaba en la lista; se omite")
                    plan["comer"] = None
                leidas = _leidas(j)
                plan["fuentes"] = [u for u, est in leidas if "SUCCESS" in est.upper()]
                plan["modelo"] = modelo
                plan["lectura"] = ", ".join(f"{u.split('/')[2] if '//' in u else u}: {est.lower()}" for u, est in leidas)
                plan["segundos"] = round(time.time() - t0)
                util.log(f"Distinto Básico: {modelo} en {time.time() - t0:.0f}s · páginas: {plan['lectura']}")
                return plan, avisos
            except Exception as e:
                avisos.append(f"Distinto Básico · {modelo} ({time.time() - t0:.0f} s): {str(e)[:200]}")
                util.log(avisos[-1])
                if "HTTP 429" in str(e) or "HTTP 5" in str(e):
                    time.sleep(10)
    return None, avisos


def para_guardar(hoy, plan):
    """La propuesta tal cual, para poder recordarla otro día si ese día no sale ninguna."""
    return dict({k: v for k, v in plan.items() if k not in ("fuentes", "lectura", "recordatorio", "segundos")},
                propuesto=hoy.isoformat())


def recordatorio(hoy, guardadas):
    """Si hoy no sale plan nuevo: una propuesta de otro día que siga en pie (con fecha de hoy a dos
    semanas), la más próxima, y que no se haya recordado ya. Devuelve el plan o None."""
    candidatas = []
    for p in guardadas or []:
        try:
            dia = dt.date.fromisoformat(str(p.get("dia"))[:10])
            propuesto = dt.date.fromisoformat(str(p.get("propuesto"))[:10])
        except (TypeError, ValueError):
            continue
        if propuesto < hoy <= dia <= hoy + dt.timedelta(days=14) and not p.get("recordado"):
            candidatas.append((dia, p))
    if not candidatas:
        return None
    dia, p = min(candidatas, key=lambda x: x[0])
    plan = dict(p, recordatorio=True, modelo="recordatorio")
    cuando = "hoy" if dia == hoy else "mañana" if dia == hoy + dt.timedelta(days=1) else f"el {util.fecha_larga(dia)}"
    m = re.match(r"^(\d{1,2}):(\d{2})$", str(p.get("hora") or ""))
    plan["cuando"] = cuando + (f", a {util.hora_hablada(int(m.group(1)), int(m.group(2)))}" if m else "")
    return plan


def linea_historial(hoy, plan):
    comer = plan.get("comer") or {}
    return " · ".join(str(x) for x in (hoy.isoformat(), plan.get("titulo"), plan.get("cuando") or plan.get("dia") or "",
                                       plan.get("lugar") or "", f"comer: {comer.get('nombre', '')}",
                                       plan.get("fuente") or "") if x)
