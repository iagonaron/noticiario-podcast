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

# Horas escritas a mano en los títulos: «9.3013.30» o «9.30-13.30» → «9:30 a 13:30», «Ferrer1430» → «Ferrer 14:30»,
# «9.30» → «9:30». Luego la voz las dice con números, tal cual («trece treinta»): así lo quiere Iago (21-oct-2026),
# para no tener dudas de qué hora es (ver pronuncia.py).
_H, _M = r"([01]?\d|2[0-3])", r"([0-5]\d)"
RE_DOS_HORAS = re.compile(rf"(?<![\d.:]){_H}[.:]{_M}\s*(?:[-–—/]|\ba\b)?\s*{_H}[.:]{_M}(?![\d.:])")
RE_HORA_PEGADA = re.compile(rf"(?<=[^\W\d_]){_H}{_M}\b")
RE_UNA_HORA = re.compile(rf"(?<![\d.:]){_H}[.:]{_M}(?![\d.:])")


def _horas(t):
    t = RE_DOS_HORAS.sub(lambda m: f"{int(m[1])}:{m[2]} a {int(m[3])}:{m[4]}", t)
    t = RE_HORA_PEGADA.sub(lambda m: f" {int(m[1])}:{m[2]}", t)
    return RE_UNA_HORA.sub(lambda m: f"{int(m[1])}:{m[2]}", t)


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
    t = util.sin_emojis(e["titulo"])
    if e["min"] is not None:
        t = RE_HORA_TITULO.sub("", t, count=1).strip(" -–·:")
    t = _horas(t)
    t = re.sub(r"\(\s*sin hora\s*\)", ", aún sin hora", t, flags=re.I)
    if "madrid" in t.lower():
        t = re.sub(r"\s*[—–-]\s*", " contra ", t, count=1)
    t = t.replace("—", ", ").replace("–", ", ").replace(" - ", ", ")
    t = re.sub(r"\s+,", ",", t)
    return re.sub(r"\s{2,}", " ", t).strip(" ,") or util.sin_emojis(e["titulo"]) or "un evento"


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


# Eventos que solo se dicen el mismo día, no la víspera (Iago, 28-oct-2026: el Depor en Riazor solo le
# importa ese día, para aparcar). Se comparan con el título en minúsculas y sin tildes.
SOLO_EL_DIA = ("depor en riazor",)


def _solo_el_dia(e):
    t = util.sin_tildes(e.get("titulo") or "").lower()
    return any(x in t for x in SOLO_EL_DIA)


def texto_plantilla(eventos, problemas=None):
    """Agenda de hoy y de mañana en dos frases."""
    hoy = eventos.get("hoy") or []
    man = [e for e in (eventos.get("manana") or []) if not _solo_el_dia(e)]
    if not hoy and not man:
        if problemas:
            return "Hoy no he podido leer tu agenda; échale un ojo en el noticiario."
        return "En la agenda, hoy y mañana, nada: días libres."
    if not hoy:
        return f"Hoy no tienes nada en la agenda. Mañana: {_lista(man, 4)}."
    texto = f"En la agenda de hoy: {_lista(hoy, 6)}."
    texto += f" Y mañana: {_lista(man, 4)}." if man else " Mañana, nada."
    return texto + _aviso_aparcar(hoy)


def _aviso_aparcar(hoy):
    """Día de partido en Riazor: cerca de casa de Iago no hay dónde aparcar desde un rato antes hasta un rato
    después, así que mejor no mover el coche (lo pidió el 28-oct-2026)."""
    partidos = [e for e in hoy if _solo_el_dia(e)]
    if not partidos:
        return ""
    e = partidos[0]
    if e.get("min") is None:
        return " Ojo, que hoy hay partido en Riazor, aún sin hora: piénsatelo antes de mover el coche."
    desde, hasta = max(0, e["min"] - 90), min(23 * 60 + 59, e["min"] + 150)   # hora y media antes, dos y media después
    return (f" Ojo con el coche: con el partido, mejor no moverlo entre {util.hora_hablada(desde // 60, desde % 60)}"
            f" y {util.hora_hablada(hasta // 60, hasta % 60)}, que no habrá dónde aparcar.")
