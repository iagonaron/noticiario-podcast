"""«En el gimnasio hoy»: las reservas del día en el gimnasio, juntas y pensadas para la franja de Iago.

Todo lo personal (la web del gimnasio, sus horas, qué actividades le molestan) vive SOLO en Dropbox,
en /Gimnasio.txt (el repositorio es público). Aquí solo está la forma de leer la web de reservas
(plataforma IsMyGym, página pública sin iniciar sesión) y la plantilla fija del texto (sin IA).

En esa página, cada franja trae un número junto a un icono de persona: son las PLAZAS LIBRES (ver `apuntados`).

Qué cuenta, en este orden de importancia (lo pidió así el 28-oct-2026):
1. Fuerza principal abajo en su franja: le molestan las clases de grupo de abajo («molestan abajo»);
   con 2 o más personas acaparan las máquinas de abajo; con 1 es un entrenamiento individual (se dice,
   pero no molesta). Si la franja choca, se busca la hora de empezar libre más cercana.
2. Spinning a partir de cierta hora («spinning desde»): los días de HIIT quiere la bici de spinning.
3. Cuánta gente entrenará por libre a esa hora (reservas de sala de máquinas + tarifa reducida), sin contarle a él.
"""
import datetime as dt
import re

from . import util

ARCHIVO = "/Gimnasio.txt"     # en la carpeta del pódcast en Dropbox

DEFECTO = {
    "mi franja principal": "10:30-11:15",
    "mi sesión entera": "10:30-12:00",
    "miro desde-hasta": "9:00-13:00",
    "molestan abajo": "Entrenamiento Personal; Super Clase Combinada (Musc)",
    "spinning": "Spinning; Super Clase Combinada (Spin)",
    "spinning desde": "11:00",
    "salas de máquinas": "Sala de máquinas; Sala de Máquinas Tarifa Reducida",
    "descontarme en sala de máquinas": "sí",
    "número de la web": "plazas libres",     # o «apuntados», si algún día se comprueba lo contrario
}


# ------------------------------------------------------------------ ajustes de Dropbox
def leer_ajustes(texto):
    aj = dict(DEFECTO)
    for linea in (texto or "").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or ":" not in linea:
            continue
        clave, valor = linea.split(":", 1)
        aj[util.sin_tildes(clave.strip().lower())] = valor.strip()
    # las claves por defecto también sin tildes, para encontrarlas igual
    return {util.sin_tildes(k): v for k, v in aj.items()}


def _min(hhmm):
    h, m = re.match(r"\s*(\d{1,2})[:.](\d{2})", hhmm).groups()
    return int(h) * 60 + int(m)


def _tramo(texto):
    a, b = re.split(r"\s*[-–a]\s*", texto.strip(), maxsplit=1)
    return _min(a), _min(b)


def _lista(texto):
    return [t.strip().lower() for t in re.split(r"[;\n]", texto or "") if t.strip()]


def _hh(m):
    return f"{m // 60}:{m % 60:02d}"


# ------------------------------------------------------------------ lectura de la web
def leer_semana(html):
    """Todas las franjas de la semana: [{sala, dia (número del mes), actividad, ini, fin (minutos), personas}]."""
    from bs4 import BeautifulSoup
    sopa = BeautifulSoup(html, "html.parser")
    primero = sopa.select_one("div.our-classes-time")
    if not primero:
        raise RuntimeError("la página de reservas no trae el cuadrante (¿ha cambiado la web?)")
    franjas, sala = [], ""
    for hijo in primero.parent.find_all(recursive=False):
        clases = hijo.get("class") or []
        if "our-classes-time" not in clases:
            t = re.sub(r"Semana (siguiente|anterior)", "", hijo.get_text(" ", strip=True)).strip()
            if hijo.name == "div" and t:
                sala = t
            continue
        for li in hijo.select("ul > li"):
            cab = li.find("p", recursive=False)
            m = re.search(r"(\d{1,2})", cab.get_text() if cab else "")
            if not m:
                continue
            dia = int(m.group(1))
            for caja in li.select(".class-time-box"):
                act = caja.select_one("a.horario")
                horas = caja.select_one(".on-hover strong")
                hm = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", horas.get_text() if horas else "")
                if not act or not hm:
                    continue
                num = None
                for sp in caja.find_all("span"):
                    if sp.get("class") and re.fullmatch(r"\s*\d+\s*", sp.get_text()):
                        num = int(sp.get_text())
                franjas.append({"sala": sala, "dia": dia, "actividad": act.get_text(strip=True),
                                "ini": _min(hm.group(1)), "fin": _min(hm.group(2)), "libres": num or 0})
    return franjas


def enlace_siguiente(html, base):
    """La dirección de «Semana siguiente» (sirve para saber el aforo de cada franja)."""
    m = re.search(r'href="([^"]*f=\d+[^"]*)"[^>]*>\s*(?:<[^>]+>\s*)*Semana siguiente', html)
    if not m:
        m = re.search(r'href="([^"]*index\.php\?[^"]*f=\d+[^"]*)"', html)
    if not m:
        return None
    import html as h
    import urllib.parse
    return urllib.parse.urljoin(base, h.unescape(m.group(1)).split("#")[0])


def _es(franja, terminos):
    nombre = franja["actividad"].lower()
    return any(t in nombre for t in terminos)


def _solapa(f, a, b):
    return f["ini"] < b and f["fin"] > a


# ------------------------------------------------------------------ el texto del pódcast
def _personas(n):
    return "1 persona" if n == 1 else f"{n} personas"


def _nombre_clase(act):
    a = act.strip()
    a = re.sub(r"\s*\(Musc\)", " de musculación", a, flags=re.I)
    a = re.sub(r"\s*\(Spin\)", " de spinning", a, flags=re.I)
    return a.lower()


def apuntados(semana, siguiente):
    """El número de la web son PLAZAS LIBRES (28-oct-2026: en la app, spinning 18:00 marcaba 12 con 6 caras
    y 20:00 marcaba 9 con 9 caras; aforo 18). Las personas apuntadas = aforo − libres. El aforo de cada franja
    es lo más alto que marca esa misma actividad y hora en esta semana y la siguiente (casi vacía)."""
    aforo = {}
    for f in semana + siguiente:
        k = (f["actividad"].lower(), f["ini"], f["fin"])
        aforo[k] = max(aforo.get(k, 0), f["libres"])
    for f in semana:
        f["aforo"] = aforo[(f["actividad"].lower(), f["ini"], f["fin"])]
        f["personas"] = max(0, f["aforo"] - f["libres"])
    return semana


def _juntar(franjas):
    """Franjas seguidas de la misma actividad → un solo tramo (con lo más lleno)."""
    salida = []
    for f in sorted(franjas, key=lambda f: f["ini"]):
        if salida and salida[-1]["actividad"] == f["actividad"] and salida[-1]["fin"] >= f["ini"]:
            salida[-1] = dict(salida[-1], fin=max(salida[-1]["fin"], f["fin"]),
                              personas=max(salida[-1]["personas"], f["personas"]))
        else:
            salida.append(dict(f))
    return salida


def _clase(f, con_hora=True):
    t = _nombre_clase(f["actividad"])
    if con_hora:
        t += f" de {_hh(f['ini'])} a {_hh(f['fin'])}"
    return t + f", con {_personas(f['personas'])}"


def resumen(franjas, hoy, aj, hiit=False):
    """Texto fijo del bloque (y un diagnóstico con las franjas usadas). Vacío si hoy no hay datos.
    `franjas` ya trae «personas» (apuntados). Con `hiit` (hoy toca empuje, que lleva HIIT), la hora también
    se elige para que la bici de spinning esté libre en el rato del HIIT."""
    del_dia = [f for f in franjas if f["dia"] == hoy.day]
    if not del_dia:
        return "", ["Gimnasio: la web no trae franjas para hoy"]
    p_ini, p_fin = _tramo(aj["mi franja principal"])
    v_ini, v_fin = _tramo(aj["miro desde-hasta"])
    h_desde, h_hasta = _tramo(aj.get("hiit tras empezar", "1:05-1:30"))     # minutos tras empezar (h:mm)
    abajo_t, spin_t, sala_t = _lista(aj["molestan abajo"]), _lista(aj["spinning"]), _lista(aj["salas de maquinas"])
    duracion = p_fin - p_ini
    descontar = util.sin_tildes(aj.get("descontarme en sala de maquinas", "si").lower()).startswith("s")

    abajo = [f for f in del_dia if _es(f, abajo_t) and f["personas"] >= 1 and _solapa(f, v_ini, v_fin)]
    grupo = _juntar([f for f in abajo if f["personas"] >= 2])        # 2 o más acaparan las máquinas de abajo
    spin = _juntar([f for f in del_dia if _es(f, spin_t) and f["personas"] >= 1])   # clase con gente = sin bici

    def choque_fuerza(ini):
        return [f for f in grupo if _solapa(f, ini, ini + duracion)]

    def choque_bici(ini):
        return [f for f in spin if _solapa(f, ini + h_desde, ini + h_hasta)] if hiit else []

    def clase(f):
        return f"{_nombre_clase(f['actividad'])} con {f['personas']} de {_hh(f['ini'])} a {_hh(f['fin'])}"

    # Una sola frase (28-oct-2026): ¿a tu hora, antes o después? (y por qué, muy breve) y cuánta gente habrá;
    # los días de HIIT, además, si tendrá la bici de spinning. Primero la fuerza; la bici, si se puede.
    candidatas = [p_ini] + [x for paso in range(5, 241, 5) for x in (p_ini - paso, p_ini + paso)
                            if v_ini <= x and x + duracion <= v_fin]
    fuerza = next((x for x in candidatas if not choque_fuerza(x)), None)        # lo primero: la fuerza
    elegido, sin_bici = fuerza, False
    if fuerza is not None and choque_bici(fuerza):
        # la bici es menos importante: solo se mueve la hora como mucho «mover por la bici» minutos más
        margen = _min(aj.get("mover por la bici", "0:30"))
        otra = next((x for x in candidatas if abs(x - fuerza) <= margen
                     and not choque_fuerza(x) and not choque_bici(x)), None)
        elegido, sin_bici = (otra, False) if otra is not None else (fuerza, True)
    motivos = []
    if elegido != p_ini:
        motivos = [clase(f) + " abajo" for f in choque_fuerza(p_ini)]
        if not sin_bici:
            motivos += [clase(f) + " en la sala de bicis" for f in choque_bici(p_ini)]

    gente = ""
    if elegido is not None:
        e_ini, e_fin = elegido, elegido + duracion
        sala = [f for f in del_dia if _es(f, sala_t) and _solapa(f, e_ini, e_fin)]
        if sala:
            puntos = sorted({e_ini} | {f["ini"] for f in sala if e_ini < f["ini"] < e_fin})
            n = max(sum(f["personas"] for f in sala if f["ini"] <= t < f["fin"]) for t in puntos)
            if descontar and n:
                n -= 1                             # él también reserva sala de máquinas: no se cuenta
            gente = f"habrá {'unas ' + str(n) + ' personas' if n > 1 else ('1 persona' if n == 1 else 'muy poca gente')}"

    bici = ""
    if hiit and elegido is not None:
        if sin_bici:
            f = choque_bici(elegido)[0]
            bici = f"para el HIIT no tendrás bici de spinning ({clase(f)}): haz el C"
        else:
            bici = "y para el HIIT tendrás la bici de spinning libre"

    if elegido is None:
        frase = "Gimnasio: hoy abajo está complicado toda la mañana: " + util.lista_hablada(
            [clase(f) for f in grupo]) + "."
    elif elegido == p_ini:
        frase = f"Gimnasio: puedes ir a tu hora, a las {_hh(p_ini)}"
    else:
        cuando = "antes" if elegido < p_ini else "más tarde"
        frase = f"Gimnasio: mejor ve {cuando}, a las {_hh(elegido)}, porque hay " + util.lista_hablada(motivos)
    if elegido is not None:
        colas = [c for c in (gente, bici) if c]
        if bici and not sin_bici and gente:
            frase += "; " + gente + " " + bici + "."
        else:
            frase += "".join("; " + c for c in colas) + "."

    diag = ["Gimnasio: " + ", ".join(f"{f['actividad']} {_hh(f['ini'])}-{_hh(f['fin'])}={f['personas']}/{f.get('aforo')}"
                                   for f in sorted(del_dia, key=lambda f: f["ini"]) if _solapa(f, v_ini, v_fin))]
    return frase, diag


def tabla(franjas, hoy, aj):
    """Tablita para el final del guion escrito: por franjas, lo que pasa en cada zona y cuánta gente."""
    del_dia = [f for f in franjas if f["dia"] == hoy.day]
    v_ini, v_fin = _tramo(aj["miro desde-hasta"])
    p_ini, p_fin = _tramo(aj["mi franja principal"])
    abajo_t, spin_t, sala_t = _lista(aj["molestan abajo"]), _lista(aj["spinning"]), _lista(aj["salas de maquinas"])
    zonas = [f for f in del_dia if _solapa(f, v_ini, v_fin) and (_es(f, abajo_t) or _es(f, spin_t) or _es(f, sala_t))]
    if not zonas:
        return ""
    cortes = sorted({v_ini, v_fin} | {f["ini"] for f in zonas if v_ini < f["ini"] < v_fin}
                    | {f["fin"] for f in zonas if v_ini < f["fin"] < v_fin})
    corto = lambda a: (re.sub(r"\s*\(Musc\)", " (musc.)", re.sub(r"\s*\(Spin\)", " (spin)", a))
                       .replace("Super Clase Combinada", "Superclase").replace("Entrenamiento Personal", "Entreno personal")
                       .replace("Spinning Clase Virtual", "Spinning virtual"))
    filas = ["| Franja | Abajo (fuerza) | Spinning | Por libre (sala) |", "|---|---|---|---|"]
    crudas = []
    for a, b in zip(cortes, cortes[1:]):
        ab = [f for f in zonas if _es(f, abajo_t) and _solapa(f, a, b) and f["personas"] >= 1]
        sp = [f for f in zonas if _es(f, spin_t) and _solapa(f, a, b)]
        sl = sum(f["personas"] for f in zonas if _es(f, sala_t) and _solapa(f, a, b))
        celda = lambda L: " · ".join(f"{corto(f['actividad'])} {f['personas']}" for f in L) or "—"
        marca = " ⭐" if _solapa({"ini": a, "fin": b}, p_ini, p_fin) else ""
        grupo = any(f["personas"] >= 2 for f in ab)
        fila = [a, b, marca, ('⚠️ ' if grupo else '') + celda(ab), celda(sp), sl]
        if crudas and crudas[-1][2:] == fila[2:] and crudas[-1][1] == a:
            crudas[-1][1] = b                      # igual que la anterior: se juntan
        else:
            crudas.append(fila)
    for a, b, marca, c1, c2, sl in crudas:
        filas.append(f"| {_hh(a)}–{_hh(b)}{marca} | {c1} | {c2} | {sl} |")
    return ("\n\n## 🏋️ Gimnasio hoy\n\n" + "\n".join(filas)
            + "\n\n_Número = personas apuntadas. ⭐ tu franja de siempre · ⚠️ clase de grupo abajo · "
              "«Por libre» = reservas de sala de máquinas + tarifa reducida (contándote a ti si reservaste)._\n")


def toca_hiit(aj):
    """¿El entreno que toca hoy lleva HIIT? Lo mira en la app de entreno (Supabase, solo lectura): el día
    siguiente al último registrado. Las claves viven en Dropbox (/Gimnasio.txt), no aquí."""
    url, clave = aj.get("entreno url"), aj.get("entreno clave")
    dias_hiit = {int(x) for x in re.findall(r"\d+", aj.get("dias con hiit", "1, 4"))}
    num = int(aj.get("dias del ciclo", "6"))
    if not url or not clave:
        return None, "Gimnasio: sin «entreno url/clave» no se mira si toca HIIT"
    import requests
    r = requests.get(url.rstrip("/") + "/rest/v1/ironbike_sesiones",
                     params={"select": "dia_ciclo,fecha", "dia_ciclo": f"gte.1", "order": "fecha.desc,id.desc", "limit": "1"},
                     headers={"apikey": clave, "Authorization": f"Bearer {clave}"}, timeout=20)
    r.raise_for_status()
    filas = r.json()
    ultimo = filas[0]["dia_ciclo"] if filas else 0
    hoy_toca = (ultimo % num) + 1 if ultimo else 1
    return hoy_toca in dias_hiit, f"Gimnasio: último entreno D{ultimo} ({filas[0]['fecha'] if filas else '-'}) → hoy D{hoy_toca}"


def texto_de_hoy(token, hoy):
    """Lee los ajustes de Dropbox y la web del gimnasio. Devuelve (texto, tabla, diagnóstico, avisos)."""
    from . import dropbox
    crudo = dropbox.descargar(token, ARCHIVO) if token else None
    if not crudo:
        return "", "", [], []                              # sin fichero de ajustes no hay bloque (es opcional)
    aj = leer_ajustes(crudo.decode("utf-8-sig", "replace"))
    web = aj.get("web")
    if not web:
        return "", "", [], [f"Gimnasio: falta la línea «web:» en {ARCHIVO}"]
    html = util.descargar(web, timeout=30, etiqueta="la web de reservas del gimnasio")
    franjas = leer_semana(html)
    siguiente, avisos = [], []
    try:
        url2 = enlace_siguiente(html, web)
        if url2:
            siguiente = leer_semana(util.descargar(url2, timeout=30, etiqueta="la semana siguiente del gimnasio"))
    except Exception as e:
        avisos.append(f"Gimnasio: no se pudo leer la semana siguiente ({type(e).__name__}); el aforo sale solo de esta")
    if util.sin_tildes(aj.get("numero de la web", "plazas libres").lower()).startswith("apuntad"):
        for f in franjas:
            f["personas"] = f["libres"]
    else:
        apuntados(franjas, siguiente)
    hiit = False
    try:
        hiit, nota = toca_hiit(aj)
        if hiit is None:
            avisos.append(nota)
        diag_hiit = [nota]
    except Exception as e:
        diag_hiit = []
        avisos.append(f"Gimnasio: no se pudo mirar qué entreno toca ({type(e).__name__})")
    texto, diag = resumen(franjas, hoy, aj, hiit=bool(hiit))
    diag = diag_hiit + diag
    return texto, tabla(franjas, hoy, aj), diag + [f"Gimnasio: {len(franjas)} franjas esta semana y {len(siguiente)} la siguiente"], avisos
