"""Festivos (de España, de Galicia y locales de A Coruña), días señalados y cambio de hora,
para decirlo al principio del programa: «hoy es festivo: …», «mañana es el Día de…»."""
import datetime as dt
import os

import holidays

AQUI = os.path.dirname(os.path.abspath(__file__))

# Festivos locales de A Coruña (los fija el Concello cada año; añadir aquí los de cada año nuevo)
LOCALES = {
    dt.date(2026, 2, 17): "Martes de Entroido",
    dt.date(2026, 10, 7): "la Festividad del Rosario",
}

# Cómo suena cada festivo de la librería en voz alta
NOMBRES = {
    "Año Nuevo": "Año Nuevo",
    "Epifanía del Señor": "el Día de Reyes",
    "San José": "San José",
    "Jueves Santo": "Jueves Santo",
    "Viernes Santo": "Viernes Santo",
    "Fiesta del Trabajo": "el Día del Trabajo",
    "San Juan": "San Juan",
    "Día Nacional de Galicia": "el Día de Galicia",
    "Asunción de la Virgen": "la Asunción",
    "Fiesta Nacional de España": "la Fiesta Nacional, el Día de la Hispanidad",
    "Todos los Santos": "Todos los Santos",
    "Día de la Constitución Española": "el Día de la Constitución",
    "Inmaculada Concepción": "la Inmaculada",
    "Natividad del Señor": "Navidad",
    "Día de las Letras Gallegas": "el Día de las Letras Gallegas",
}


def _festivos(anio):
    try:
        return holidays.country_holidays("ES", subdiv="GA", years=[anio], language="es")
    except Exception:
        return {}


def _dias(anio):
    salida = {}
    ruta = os.path.join(AQUI, "..", "dias_senalados.txt")
    try:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                if linea.strip().startswith("#") or "|" not in linea:
                    continue
                fecha, nombre = (p.strip() for p in linea.split("|", 1))
                mes, dia = (int(x) for x in fecha.split("-"))
                salida[dt.date(anio, mes, dia)] = nombre
    except (OSError, ValueError):
        pass
    return salida


def _ultimo_domingo(anio, mes):
    d = dt.date(anio, mes, 31)
    while d.weekday() != 6:
        d -= dt.timedelta(days=1)
    return d


def _con_articulo(nombre):
    n = nombre.strip()
    return n if n.lower().startswith(("el ", "la ", "los ", "las ")) or n[0].islower() else n


def frases(fecha, cuando):
    """Lo que hay que decir de un día concreto («Hoy» o «Mañana»)."""
    out = []
    fest = _festivos(fecha.year).get(fecha)
    if fest:
        out.append(f"{cuando} es festivo: {NOMBRES.get(fest, fest)}")
    if fecha in LOCALES:
        out.append(f"{cuando} es festivo en A Coruña: {LOCALES[fecha]}")
    dia = _dias(fecha.year).get(fecha)
    if dia:
        out.append(f"{cuando} es {_con_articulo(dia)}" if not dia.lower().startswith("día") else f"{cuando} es el {dia}")
    # cambio de hora (madrugada del último domingo de marzo y de octubre)
    for mes, texto in ((3, "se adelanta la hora: a las dos serán las tres, así que dormirás una hora menos"),
                       (10, "se atrasa la hora: a las tres volverán a ser las dos, así que tienes una hora más")):
        domingo = _ultimo_domingo(fecha.year, mes)
        if fecha == domingo - dt.timedelta(days=1):
            out.append(("Esta noche" if cuando == "Hoy" else "Mañana por la noche") + " " + texto)
        elif fecha == domingo and cuando == "Hoy":
            out.append("Esta madrugada se ha cambiado la hora; revisa los relojes que no se ajustan solos")
    return out


def texto(hoy):
    partes = frases(hoy, "Hoy") + frases(hoy + dt.timedelta(days=1), "Mañana")
    return " ".join(p[0].upper() + p[1:] + "." for p in partes)
