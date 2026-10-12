"""Cumpleaños y días señalados, al principio del programa (plantilla fija, sin IA).

La lista vive en `Cumpleaños.txt` dentro de la carpeta del pódcast en Dropbox (si no está,
se usa la copia del repositorio, `cumpleanos.txt`). Formato, el mismo en que la escribió Iago:

    Marzo
    Día del padre 19
    Evaristo 25
    Mayo
    Día de la madre (1º domingo)

Si una línea trae el mes al final («Carla 20 febrero»), manda ese mes.
"""
import datetime as dt
import re
import unicodedata

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
ORDINALES = {"1": 1, "2": 2, "3": 3, "4": 4, "primer": 1, "primero": 1, "segundo": 2, "tercer": 3,
             "tercero": 3, "cuarto": 4, "último": -1, "ultimo": -1}


def _sin_tildes(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _mes(palabra):
    p = _sin_tildes(palabra.strip().lower())
    for i, m in enumerate(MESES, 1):
        if p == _sin_tildes(m) or (p == "setiembre" and m == "septiembre"):
            return i
    return None


def leer(texto):
    """→ lista de {'nombre', 'mes', 'dia'} o {'nombre', 'mes', 'regla': (n, dia_semana)}."""
    entradas, mes = [], None
    for linea in (texto or "").splitlines():
        l = linea.strip()
        if not l or l.startswith("(") or l.upper() == "CUMPLEAÑOS":
            continue
        if _mes(l):
            mes = _mes(l)
            continue
        if mes is None:
            continue
        # regla del tipo «(1º domingo)», «(primer domingo)», «(último domingo)»
        m = re.search(r"\((\w+)\.?\s+(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\)", l, re.I)
        if m:
            g = re.sub(r"[º°ª]$", "", m.group(1).lower())
            if re.fullmatch(r"\d+o", g):          # «1o» escrito sin el símbolo de ordinal
                g = g[:-1]
            n = ORDINALES.get(g)
            ds = [_sin_tildes(d) for d in DIAS_SEMANA].index(_sin_tildes(m.group(2).lower()))
            nombre = l[:m.start()].strip()
            if n and nombre:
                entradas.append({"nombre": nombre, "mes": mes, "regla": (n, ds)})
            continue
        m = re.match(r"^(.*?)\s+(\d{1,2})(?:\s+(?:de\s+)?([A-Za-zÁÉÍÓÚáéíóú]+))?\s*$", l)
        if m:
            mes_l = _mes(m.group(3)) if m.group(3) else None
            entradas.append({"nombre": m.group(1).strip(), "mes": mes_l or mes, "dia": int(m.group(2))})
    return entradas


def _fecha(entrada, anio):
    if "dia" in entrada:
        try:
            return dt.date(anio, entrada["mes"], entrada["dia"])
        except ValueError:
            return None
    n, ds = entrada["regla"]
    if n == -1:
        d = dt.date(anio + (entrada["mes"] == 12), entrada["mes"] % 12 + 1, 1) - dt.timedelta(days=1)
        while d.weekday() != ds:
            d -= dt.timedelta(days=1)
        return d
    d = dt.date(anio, entrada["mes"], 1)
    while d.weekday() != ds:
        d += dt.timedelta(days=1)
    return d + dt.timedelta(weeks=n - 1)


def _es_dia_senalado(nombre):
    n = _sin_tildes(nombre.lower())
    return n.startswith(("dia ", "san ", "santa ", "santo "))


def _frase(nombres, cuando):
    personas = [n for n in nombres if not _es_dia_senalado(n)]
    dias = [n for n in nombres if _es_dia_senalado(n)]
    frases = []
    if dias:
        frases.append(f"{cuando} es " + " y ".join(("el " + d[0].lower() + d[1:]) if d.lower().startswith("día") else d
                                                    for d in dias))
    if personas:
        def nom(p):
            return p[0].lower() + p[1:] if p.lower() in ("mamá", "papá") else p
        lista = [nom(p) for p in personas]
        if len(lista) == 1 and " y " not in lista[0]:
            frases.append(f"{cuando} es el cumpleaños de {lista[0]}")
        else:
            todos = ", ".join(lista[:-1]) + " y " + lista[-1] if len(lista) > 1 else lista[0]
            frases.append(f"{cuando} es el cumpleaños de {todos}")
    return frases


def texto(entradas, hoy):
    hoy_n = [e["nombre"] for e in entradas if _fecha(e, hoy.year) == hoy]
    man = hoy + dt.timedelta(days=1)
    man_n = [e["nombre"] for e in entradas if _fecha(e, man.year) == man]
    partes = []
    if hoy_n:
        t = ". ".join(_frase(hoy_n, "hoy")) + "."
        if any(not _es_dia_senalado(n) for n in hoy_n):
            t += " No te olvides de felicitar."
        partes.append("Antes de nada: " + t)
    if man_n:
        partes.append(". ".join(_frase(man_n, "Mañana")) + ".")
    return " ".join(partes)
