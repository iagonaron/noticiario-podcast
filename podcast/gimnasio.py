"""«En el gimnasio hoy»: las reservas del día en el gimnasio, juntas y pensadas para la franja de Iago.

Todo lo personal (la web del gimnasio, sus horas, qué actividades le molestan) vive SOLO en Dropbox,
en /Gimnasio.txt (el repositorio es público). Aquí solo está la forma de leer la web de reservas
(plataforma IsMyGym, página pública sin iniciar sesión) y la plantilla fija del texto (sin IA).

En esa página, cada franja trae un número junto a un icono de persona: son las PLAZAS LIBRES (ver `apuntados`).

Qué cuenta, en este orden de importancia (lo pidió así el 28-oct-2026):
1. Fuerza principal abajo en su franja: le molestan las clases de abajo («molestan abajo»: entrenamiento
   personal y la combinada de musculación). Primero se busca la hora de empezar más cercana con abajo libre
   DEL TODO, sin nadie apuntado (30-oct-2026: «prefiero que si hay una hora libre del todo ir a esa hora»;
   ese día un entrenamiento personal de 1 persona a las 11:00 le pisaba la pierna y lo bueno era 10:00-11:00).
   Si en toda la mañana no hay un hueco así, vale con que no haya clases de 2 o más (las que acaparan
   las máquinas). El spinning no cuenta aquí: es otra sala.
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
            dsem = util.sin_tildes(cab.get_text(" ", strip=True)).lower()[:3]      # lun, mar, mie, jue…
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
                franjas.append({"sala": sala, "dia": dia, "dsem": dsem, "actividad": act.get_text(strip=True),
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
    y 20:00 marcaba 9 con 9 caras; aforo 18; 29-oct: entrenamiento personal 19:00 marcaba 3 con 12 caras,
    aforo 15). Personas apuntadas = aforo − libres.
    El aforo de cada franja es lo más alto que marca ESA MISMA franja (misma actividad, mismo día de la semana
    y misma hora) en esta semana y las siguientes, que están casi vacías. OJO: no se mezclan días distintos:
    el 29-oct salió «5 personas» en el entrenamiento personal del jueves a las 11 porque se tomó el aforo del
    lunes (15) y el del jueves es 10, sin nadie apuntado."""
    clave = lambda f: (f["actividad"].lower(), f.get("dsem"), f["ini"], f["fin"])
    aforo = {}
    for f in semana + siguiente:
        aforo[clave(f)] = max(aforo.get(clave(f), 0), f["libres"])
    for f in semana:
        f["aforo"] = aforo[clave(f)]
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
    todas = _juntar(abajo)                                           # abajo libre del todo (lo que prefiere)
    grupo = _juntar([f for f in abajo if f["personas"] >= 2])        # 2 o más acaparan las máquinas de abajo
    spin = _juntar([f for f in del_dia if _es(f, spin_t) and f["personas"] >= 1])   # clase con gente = sin bici
    molesta = todas

    def choque_fuerza(ini):
        return [f for f in molesta if _solapa(f, ini, ini + duracion)]

    def choque_bici(ini):
        return [f for f in spin if _solapa(f, ini + h_desde, ini + h_hasta)] if hiit else []

    def clase(f):
        return f"{_nombre_clase(f['actividad'])} con {f['personas']} de {_hh(f['ini'])} a {_hh(f['fin'])}"

    # Una sola frase (28-oct-2026): ¿a tu hora, antes o después? (y por qué, muy breve) y cuánta gente habrá;
    # los días de HIIT, además, si tendrá la bici de spinning. Primero la fuerza; la bici, si se puede.
    candidatas = [p_ini] + [x for paso in range(5, 241, 5) for x in (p_ini - paso, p_ini + paso)
                            if v_ini <= x and x + duracion <= v_fin]
    fuerza = next((x for x in candidatas if not choque_fuerza(x)), None)        # lo primero: la fuerza
    if fuerza is None:                     # ningún hueco libre del todo: basta con que no haya clases de 2 o más
        molesta = grupo
        fuerza = next((x for x in candidatas if not choque_fuerza(x)), None)
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


def _corto(a):
    return (re.sub(r"\s*\(Musc\)", " (musc.)", re.sub(r"\s*\(Spin\)", " (spin)", a))
            .replace("Super Clase Combinada", "Superclase").replace("Entrenamiento Personal", "Entreno personal")
            .replace("Spinning Clase Virtual", "Spinning virtual"))


def filas_tabla(franjas, hoy, aj):
    """Las filas de la tabla por franjas: [{ini, fin, mia, grupo, abajo, spin, sala}] (textos ya cortos)."""
    del_dia = [f for f in franjas if f["dia"] == hoy.day]
    v_ini, v_fin = _tramo(aj["miro desde-hasta"])
    p_ini, p_fin = _tramo(aj["mi franja principal"])
    abajo_t, spin_t, sala_t = _lista(aj["molestan abajo"]), _lista(aj["spinning"]), _lista(aj["salas de maquinas"])
    zonas = [f for f in del_dia if _solapa(f, v_ini, v_fin) and (_es(f, abajo_t) or _es(f, spin_t) or _es(f, sala_t))]
    if not zonas:
        return []
    cortes = sorted({v_ini, v_fin} | {f["ini"] for f in zonas if v_ini < f["ini"] < v_fin}
                    | {f["fin"] for f in zonas if v_ini < f["fin"] < v_fin})
    celda = lambda L: " · ".join(f"{_corto(f['actividad'])} {f['personas']}" for f in L) or "—"
    salida = []
    for a, b in zip(cortes, cortes[1:]):
        ab = [f for f in zonas if _es(f, abajo_t) and _solapa(f, a, b) and f["personas"] >= 1]
        sp = [f for f in zonas if _es(f, spin_t) and _solapa(f, a, b)]
        fila = {"ini": _hh(a), "fin": _hh(b), "mia": _solapa({"ini": a, "fin": b}, p_ini, p_fin),
                "grupo": any(f["personas"] >= 2 for f in ab), "abajo": celda(ab), "spin": celda(sp),
                "sala": sum(f["personas"] for f in zonas if _es(f, sala_t) and _solapa(f, a, b))}
        igual = salida and all(salida[-1][k] == fila[k] for k in ("mia", "grupo", "abajo", "spin", "sala"))
        if igual and salida[-1]["fin"] == fila["ini"]:
            salida[-1]["fin"] = fila["fin"]            # igual que la anterior: se juntan
        else:
            salida.append(fila)
    return salida


def tabla(filas):
    """Tabla en Markdown para el final del guion escrito."""
    if not filas:
        return ""
    lineas = ["| Franja | Abajo (fuerza) | Spinning | Por libre (sala) |", "|---|---|---|---|"]
    for f in filas:
        lineas.append(f"| {f['ini']}–{f['fin']}{' ⭐' if f['mia'] else ''} | {'⚠️ ' if f['grupo'] else ''}{f['abajo']} | "
                      f"{f['spin']} | {f['sala']} |")
    return ("\n\n## 🏋️ Gimnasio hoy\n\n" + "\n".join(lineas)
            + "\n\n_Número = personas apuntadas. ⭐ tu franja de siempre · ⚠️ clase de grupo abajo · "
              "«Por libre» = reservas de sala de máquinas + tarifa reducida (contándote a ti si reservaste)._\n")


def lineas_correo(filas):
    """Lo mismo, una franja por línea: el correo no dibuja tablas (29-oct-2026)."""
    out = []
    for f in filas:
        marca = (("⭐" if f["mia"] else "") + ("⚠️" if f["grupo"] else "")) or "▫️"
        abajo = "libre" if f["abajo"] == "—" else f["abajo"]
        spin = "libre" if f["spin"] == "—" else f["spin"]
        out.append(f"{marca} {f['ini']}–{f['fin']} · Abajo: {abajo} · Bici: {spin} · Por libre: {f['sala']}")
    return "\n".join(out)


def publicar_en_app(aj, hoy, frase, filas):
    """La tabla del día, a la app de entreno (Supabase, ironbike_gimnasio), para verla bonita en
    https://entreno-ironbike.netlify.app/#gimnasio (el enlace va en el correo)."""
    url, clave = aj.get("entreno url"), aj.get("entreno clave")
    if not url or not clave:
        return "sin claves"
    import requests
    r = requests.post(url.rstrip("/") + "/rest/v1/ironbike_gimnasio", params={"on_conflict": "fecha"},
                      json={"fecha": hoy.isoformat(), "frase": frase, "filas": filas},
                      headers={"apikey": clave, "Authorization": f"Bearer {clave}", "Content-Type": "application/json",
                               "Prefer": "resolution=merge-duplicates,return=minimal"}, timeout=20)
    return "ok" if r.status_code < 300 else f"HTTP {r.status_code}"


PARA_CORREO = ""        # frase + franjas en líneas + enlace (lo escribe main.py en Dropbox /Gimnasio hoy.md)


def solo_la_hora(frase):
    """Para el pódcast (28-oct-2026, «sin más explicaciones»): solo si va a su hora, antes o más tarde.
    La frase completa, con el motivo, y la tabla van en el correo «Ocupación GYM y repositorios»."""
    m = re.match(r"Gimnasio: (puedes ir a tu hora, a las [\d:]+|mejor ve (?:antes|más tarde), a las [\d:]+)", frase or "")
    if m:
        bici = ""                                    # los días de HIIT, sí o no a la bici de spinning (lo pidió)
        if "tendrás la bici de spinning libre" in frase:
            bici = ", y tendrás bici de spinning para el HIIT"
        elif "no tendrás bici de spinning" in frase:
            bici = "; hoy no habrá bici de spinning para el HIIT"
        return f"Gimnasio: {m.group(1)}{bici}."
    return "Gimnasio: hoy abajo está complicado toda la mañana." if frase else ""


def dia_que_toca(aj):
    """Qué día del ciclo toca hoy (1…N): el siguiente al último entreno registrado en la app (Supabase, solo
    lectura). Las claves viven en Dropbox (/Gimnasio.txt), no aquí. Devuelve (día o None, nota)."""
    url, clave = aj.get("entreno url"), aj.get("entreno clave")
    num = int(aj.get("dias del ciclo", "6"))
    if not url or not clave:
        return None, "Gimnasio: sin «entreno url/clave» no se mira qué entreno toca"
    import requests
    r = requests.get(url.rstrip("/") + "/rest/v1/ironbike_sesiones",
                     params={"select": "dia_ciclo,fecha", "dia_ciclo": f"gte.1", "order": "fecha.desc,id.desc", "limit": "1"},
                     headers={"apikey": clave, "Authorization": f"Bearer {clave}"}, timeout=20)
    r.raise_for_status()
    filas = r.json()
    ultimo = filas[0]["dia_ciclo"] if filas else 0
    hoy_toca = (ultimo % num) + 1 if ultimo else 1
    return hoy_toca, f"Gimnasio: último entreno D{ultimo} ({filas[0]['fecha'] if filas else '-'}) → hoy D{hoy_toca}"


def toca_hiit(aj, dia=None):
    """¿El entreno que toca hoy lleva HIIT? (None si no se sabe qué día toca)."""
    if dia is None:
        dia, nota = dia_que_toca(aj)
    else:
        nota = f"Gimnasio: hoy D{dia}"
    if dia is None:
        return None, nota
    return dia in {int(x) for x in re.findall(r"\d+", aj.get("dias con hiit", "1, 4"))}, nota


def minutos_abajo(aj, dia):
    """Cuánto rato estará abajo ese día del ciclo («abajo por dia: D2 1:00; D5 1:00» en /Gimnasio.txt). Los días
    que no salen ahí usan «mi franja principal». Devuelve minutos o None."""
    for d, hm in re.findall(r"D?\s*(\d+)\s*[=:]?\s*(\d{1,2}[:.]\d{2})", aj.get("abajo por dia", "")):
        if dia is not None and int(d) == dia:
            return _min(hm)
    return None


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
    try:                                    # las dos semanas siguientes (casi vacías) dan el aforo de cada franja
        pagina, url = html, web
        for _ in range(2):
            url = enlace_siguiente(pagina, url)
            if not url:
                break
            pagina = util.descargar(url, timeout=30, etiqueta="la semana siguiente del gimnasio")
            siguiente += leer_semana(pagina)
    except Exception as e:
        avisos.append(f"Gimnasio: no se pudieron leer las semanas siguientes ({type(e).__name__}); el aforo sale de lo que haya")
    if util.sin_tildes(aj.get("numero de la web", "plazas libres").lower()).startswith("apuntad"):
        for f in franjas:
            f["personas"] = f["libres"]
    else:
        apuntados(franjas, siguiente)
    hiit, dia = False, None
    try:
        dia, nota = dia_que_toca(aj)
        if dia is None:
            avisos.append(nota)
        hiit, _ = toca_hiit(aj, dia) if dia is not None else (None, "")
        diag_hiit = [nota]
        rato = minutos_abajo(aj, dia)
        if rato:          # ese día todo el entreno es abajo: la franja que se protege dura más (29-oct-2026)
            p_ini, p_fin = _tramo(aj["mi franja principal"])
            aj["mi franja principal"] = f"{_hh(p_ini)}-{_hh(p_ini + rato)}"
            diag_hiit.append(f"Gimnasio: hoy D{dia}, abajo {rato} min → franja {aj['mi franja principal']}")
    except Exception as e:
        diag_hiit = []
        avisos.append(f"Gimnasio: no se pudo mirar qué entreno toca ({type(e).__name__})")
    texto, diag = resumen(franjas, hoy, aj, hiit=bool(hiit))
    diag = diag_hiit + diag
    filas = filas_tabla(franjas, hoy, aj)
    global PARA_CORREO
    PARA_CORREO = (f"{texto}\n\n{lineas_correo(filas)}\n\n⭐ tu franja · ⚠️ clase de grupo abajo · números = personas apuntadas"
                   f"\n📊 Tabla: https://entreno-ironbike.netlify.app/#gimnasio") if filas else texto
    try:
        diag.append(f"Gimnasio: tabla a la app → {publicar_en_app(aj, hoy, texto, filas)}")
    except Exception as e:
        avisos.append(f"Gimnasio: no se pudo subir la tabla a la app ({type(e).__name__})")
    return texto, tabla(filas), diag + [f"Gimnasio: {len(franjas)} franjas esta semana y {len(siguiente)} las siguientes"], avisos
