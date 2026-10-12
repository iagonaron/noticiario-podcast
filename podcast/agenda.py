"""La agenda de hoy y de mañana a partir de las direcciones iCal secretas de Google Calendar.

Se lee con una plantilla fija (nunca pasa por el guionista), para que las horas no se puedan
cambiar. Igual que el noticiario:
- los eventos de todo el día con la hora escrita en el título («21h Betis – Real Madrid»)
  se tratan como eventos con hora (convención de Iago);
- y además aquí sí se tienen en cuenta los eventos que se repiten (clases semanales, etc.).
"""
import datetime as dt
import os
import re

import icalendar
import recurring_ical_events

from . import util

RE_HORA_TITULO = re.compile(r"(?:\b|^)(\d{1,2})\s*(?:[:.]\s*(\d{2}))?\s*h\b", re.I)


def _urls():
    urls = []
    for linea in os.environ.get("CALENDARIOS_ICS", "").replace(",", "\n").splitlines():
        m = re.search(r"(https?://\S+|webcal://\S+)", linea.strip())
        if m:
            urls.append(m.group(1).replace("webcal://", "https://"))
    return urls


def _a_madrid(valor):
    if isinstance(valor, dt.datetime):
        return valor.replace(tzinfo=util.MADRID) if valor.tzinfo is None else valor.astimezone(util.MADRID)
    return valor


def _eventos_del_dia(cal, dia):
    inicio = dt.datetime(dia.year, dia.month, dia.day, tzinfo=util.MADRID)
    fin = inicio + dt.timedelta(days=1)
    salida = []
    for ev in recurring_ical_events.of(cal).between(inicio, fin):
        if str(ev.get("STATUS", "")).upper() == "CANCELLED" or not ev.get("DTSTART"):
            continue
        titulo = str(ev.get("SUMMARY", "") or "(sin título)").strip()
        ini = ev.get("DTSTART").dt
        if not isinstance(ini, dt.datetime):
            fin_ev = ev.get("DTEND").dt if ev.get("DTEND") else ini + dt.timedelta(days=1)
            if not (ini <= dia < fin_ev):
                continue
            m = RE_HORA_TITULO.search(titulo)
            if m and int(m.group(1)) <= 23:
                minuto = int(m.group(1)) * 60 + int(m.group(2) or 0)
                salida.append({"min": minuto, "todo_dia": False, "titulo": titulo})
            else:
                salida.append({"min": None, "todo_dia": True, "titulo": titulo})
        else:
            ini = _a_madrid(ini)
            if inicio <= ini < fin:
                salida.append({"min": ini.hour * 60 + ini.minute, "todo_dia": False, "titulo": titulo})
            else:   # empezó antes y sigue ese día
                salida.append({"min": None, "todo_dia": True, "titulo": titulo})
    return salida


def obtener(hoy):
    """→ ({'hoy': [...], 'manana': [...]}, problemas). Cada evento: min, todo_dia, titulo, hora."""
    urls = _urls()
    if not urls:
        return {"hoy": [], "manana": []}, ["No hay calendarios configurados (secreto CALENDARIOS_ICS vacío)."]
    dias = {"hoy": hoy, "manana": hoy + dt.timedelta(days=1)}
    res = {k: [] for k in dias}
    vistos = {k: set() for k in dias}
    problemas = []
    for n, url in enumerate(urls, 1):
        try:
            cal = icalendar.Calendar.from_ical(util.descargar(url, como="bytes", timeout=30, etiqueta=f"el calendario {n}"))
            for clave, dia in dias.items():
                for e in _eventos_del_dia(cal, dia):
                    k = (e["titulo"].lower(), e["min"])
                    if k not in vistos[clave]:
                        vistos[clave].add(k)
                        res[clave].append(e)
        except Exception as e:
            # sin la dirección ni el contenido: el repositorio y sus registros son públicos
            detalle = str(e) if isinstance(e, RuntimeError) and "://" not in str(e) else type(e).__name__
            problemas.append(f"Calendario {n}: no se pudo leer ({detalle[:120]})")
    for lista in res.values():
        lista.sort(key=lambda e: (-1 if e["todo_dia"] else e["min"]))
        for e in lista:
            e["hora"] = None if e["min"] is None else f"{e['min'] // 60:02d}:{e['min'] % 60:02d}"
    return res, problemas


def _titulo(e):
    """«21h Betis – Real Madrid» → «Betis contra Real Madrid» (la hora ya se dice aparte)."""
    t = e["titulo"]
    if e["min"] is not None:
        t = RE_HORA_TITULO.sub("", t, count=1).strip(" -–·:")
    t = re.sub(r"\(\s*sin hora\s*\)", ", aún sin hora", t, flags=re.I)
    if "madrid" in t.lower():
        t = re.sub(r"\s*[–-]\s*", " contra ", t, count=1)
    t = t.replace("–", ", ").replace(" - ", ", ")
    t = re.sub(r"\s+,", ",", t)
    return re.sub(r"\s{2,}", " ", t).strip(" ,") or e["titulo"]


def _lista(eventos, maximo):
    trozos = []
    for e in eventos[:maximo]:
        if e["todo_dia"]:
            trozos.append(_titulo(e))
        else:
            trozos.append(f"a {util.hora_hablada(e['min'] // 60, e['min'] % 60)}, {_titulo(e)}")
    resto = len(eventos) - maximo
    if resto > 0:
        trozos.append(f"{resto} cosa{'s' if resto > 1 else ''} más")
    return "; ".join(trozos[:-1]) + ("; y " if len(trozos) > 1 else "") + trozos[-1] if trozos else ""


def texto_plantilla(eventos, problemas=None):
    """Agenda de hoy y de mañana en dos frases."""
    hoy, man = eventos.get("hoy") or [], eventos.get("manana") or []
    if not hoy and not man:
        if problemas:
            return "Hoy no he podido leer tu agenda; échale un ojo en el noticiario."
        return "En la agenda, hoy y mañana, nada: días libres."
    if not hoy:
        return f"Hoy no tienes nada en la agenda. Mañana: {_lista(man, 4)}."
    texto = f"En la agenda de hoy: {_lista(hoy, 6)}."
    texto += f" Y mañana: {_lista(man, 4)}." if man else " Mañana, nada."
    return texto
