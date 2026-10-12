"""La agenda de hoy a partir de las direcciones iCal secretas de Google Calendar.

Se leen con una plantilla fija (nunca pasa por el guionista), para que las horas
no se puedan cambiar. Igual que el noticiario:
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
    bruto = os.environ.get("CALENDARIOS_ICS", "")
    urls = []
    for linea in bruto.replace(",", "\n").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        # se admite «Nombre | url» o «Nombre: url» por si algún día los quieres etiquetar
        m = re.search(r"(https?://\S+|webcal://\S+)", linea)
        if m:
            urls.append(m.group(1).replace("webcal://", "https://"))
    return urls


def _a_madrid(valor):
    if isinstance(valor, dt.datetime):
        if valor.tzinfo is None:
            return valor.replace(tzinfo=util.MADRID)
        return valor.astimezone(util.MADRID)
    return valor


def obtener(hoy):
    """Lista de eventos de hoy: [{'hora': 'HH:MM' | None, 'min': int|None, 'titulo': str, 'todo_dia': bool}]"""
    urls = _urls()
    problemas = []
    if not urls:
        return [], ["No hay calendarios configurados (secreto CALENDARIOS_ICS vacío)."]
    inicio = dt.datetime(hoy.year, hoy.month, hoy.day, tzinfo=util.MADRID)
    fin = inicio + dt.timedelta(days=1)
    eventos, vistos = [], set()
    for n, url in enumerate(urls, 1):
        try:
            texto = util.descargar(url, como="bytes", timeout=30, etiqueta=f"el calendario {n}")
            cal = icalendar.Calendar.from_ical(texto)
            for ev in recurring_ical_events.of(cal).between(inicio, fin):
                if str(ev.get("STATUS", "")).upper() == "CANCELLED":
                    continue
                titulo = str(ev.get("SUMMARY", "") or "(sin título)").strip()
                ini = ev.get("DTSTART").dt if ev.get("DTSTART") else None
                if ini is None:
                    continue
                todo_dia = not isinstance(ini, dt.datetime)
                if todo_dia:
                    fin_ev = ev.get("DTEND").dt if ev.get("DTEND") else ini + dt.timedelta(days=1)
                    if not (ini <= hoy < fin_ev):
                        continue
                    m = RE_HORA_TITULO.search(titulo)
                    if m and int(m.group(1)) <= 23:
                        h, mi = int(m.group(1)), int(m.group(2) or 0)
                        evento = {"min": h * 60 + mi, "todo_dia": False}
                    else:
                        evento = {"min": None, "todo_dia": True}
                else:
                    ini = _a_madrid(ini)
                    if not (inicio <= ini < fin):
                        # empezó ayer y sigue hoy: lo contamos como «todo el día»
                        evento = {"min": None, "todo_dia": True}
                    else:
                        evento = {"min": ini.hour * 60 + ini.minute, "todo_dia": False}
                evento["titulo"] = titulo
                clave = (titulo.lower(), evento["min"])
                if clave in vistos:
                    continue
                vistos.add(clave)
                eventos.append(evento)
        except Exception as e:
            # sin la dirección: el repositorio y sus registros son públicos
            # ni el contenido del calendario (los errores de lectura pueden citar líneas del archivo)
            detalle = str(e) if isinstance(e, RuntimeError) and "://" not in str(e) else type(e).__name__
            problemas.append(f"Calendario {n}: no se pudo leer ({detalle[:120]})")
    eventos.sort(key=lambda e: (-1 if e["todo_dia"] else e["min"]))
    for e in eventos:
        e["hora"] = None if e["min"] is None else f"{e['min'] // 60:02d}:{e['min'] % 60:02d}"
    return eventos, problemas


def _titulo_sin_hora(e):
    """«21h Betis – Real Madrid» → «Betis – Real Madrid» (la hora ya se dice aparte)."""
    t = e["titulo"]
    if e["min"] is not None:
        t = RE_HORA_TITULO.sub("", t, count=1).strip(" -–·:")
    t = re.sub(r"\(\s*sin hora\s*\)", ", aún sin hora", t, flags=re.I)
    if "madrid" in t.lower():
        t = re.sub(r"\s*[–-]\s*", " contra ", t, count=1)
    t = t.replace("–", ", ").replace(" - ", ", ")
    t = re.sub(r"\s+,", ",", t)
    return re.sub(r"\s{2,}", " ", t).strip(" ,") or e["titulo"]


def texto_plantilla(eventos, problemas=None):
    """El bloque de la agenda, tal cual se va a leer."""
    if not eventos:
        if problemas and not eventos:
            return "Hoy no he podido leer tu agenda, así que échale un vistazo en el noticiario."
        return "En tu agenda de hoy no hay nada apuntado."
    todo_dia = [e for e in eventos if e["todo_dia"]]
    con_hora = [e for e in eventos if not e["todo_dia"]]
    frases = []
    if len(eventos) == 1:
        e = eventos[0]
        if e["todo_dia"]:
            return f"En tu agenda de hoy solo hay una cosa, para todo el día: {_titulo_sin_hora(e)}."
        return (f"En tu agenda de hoy solo hay una cosa: a {util.hora_hablada(e['min'] // 60, e['min'] % 60)}, "
                f"{_titulo_sin_hora(e)}.")
    n = len(eventos)
    frases.append(f"En tu agenda de hoy hay {util.NUMEROS.get(n, str(n)) if n <= 12 else n} cosas.")
    if todo_dia:
        frases.append("Para todo el día: " + util.lista_hablada([_titulo_sin_hora(e) for e in todo_dia[:4]]) + ".")
    trozos = [f"a {util.hora_hablada(e['min'] // 60, e['min'] % 60)}, {_titulo_sin_hora(e)}" for e in con_hora[:8]]
    if trozos:
        frase = ("Y con hora: " if todo_dia else "") + "; ".join(trozos[:-1]) \
                + ("; y " if len(trozos) > 1 else "") + trozos[-1] + "."
        frases.append(frase[0].upper() + frase[1:])
    if len(con_hora) > 8:
        frases.append(f"Y {len(con_hora) - 8} más que puedes ver en el noticiario.")
    texto = " ".join(frases)
    return texto[0].upper() + texto[1:]
