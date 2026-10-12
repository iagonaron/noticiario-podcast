"""El tiempo de hoy en A Coruña, con la MISMA lógica que la pantalla «Hoy» del noticiario
(función cargarTiempoMG de noticiarioiago.netlify.app):

- Temperatura y estado del cielo hora a hora: MeteoGalicia (producto horario).
- Viento: MeteoGalicia (icoVento), en bandas.
- UV: el máximo del día de MeteoGalicia, repartido por horas según la altura del sol.
- Probabilidad de lluvia por hora: Open-Meteo (si falla, la de MeteoGalicia por franjas).
- Milímetros por hora: AEMET (si falla, Open-Meteo).
Si MeteoGalicia no responde, todo sale de Open-Meteo, igual que hace el noticiario.
Además se añaden las rachas de Open-Meteo, que el noticiario no pinta pero el pódcast sí comenta.
"""
import datetime as dt
import math
import re
import xml.etree.ElementTree as ET

from . import config, util

MG_DIARIA = "https://servizos.meteogalicia.gal/mgrss/predicion/jsonPredConcellos.action?idConc={c}"
MG_HORARIA = "https://servizos.meteogalicia.gal/mgrss/predicion/jsonPredHorariaConcellos.action?idConc={c}"
AEMET_XML = "https://www.aemet.es/xml/municipios_h/localidad_h_{c}.xml"
OPEN_METEO = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
              "&hourly=temperature_2m,precipitation,precipitation_probability,uv_index,uv_index_clear_sky,"
              "windspeed_10m,windgusts_10m,weathercode&timezone=Europe%2FMadrid&forecast_days=2")
H0 = 8   # como el noticiario: de las ocho a medianoche

CEO_A_WMO = {"101": 0, "102": 1, "103": 2, "104": 3, "105": 3, "106": 45, "107": 80, "108": 81,
             "109": 71, "110": 51, "111": 61, "112": 71, "113": 95, "114": 45, "115": 45, "116": 2,
             "117": 61, "118": 80, "119": 95, "120": 71, "121": 96, "122": 80, "123": 71, "124": 45,
             "125": 3}
WMO_TEXTO = {0: "despejado", 1: "poco nuboso", 2: "nubes y claros", 3: "nublado", 45: "niebla",
             48: "niebla", 51: "llovizna", 53: "llovizna", 55: "llovizna intensa", 61: "lluvia débil",
             63: "lluvia", 65: "lluvia fuerte", 71: "nieve", 73: "nieve", 75: "nieve fuerte",
             80: "chubascos", 81: "chubascos fuertes", 82: "chubascos muy fuertes", 95: "tormenta",
             96: "tormenta con granizo", 99: "tormenta con granizo"}
GRAVEDAD = {0: 0, 1: 1, 2: 2, 3: 3, 45: 4, 48: 4, 51: 5, 53: 5, 55: 6, 61: 6, 63: 7, 65: 8,
            80: 7, 81: 8, 82: 9, 71: 8, 73: 8, 75: 9, 95: 10, 96: 10, 99: 10}
FRANJAS = {"mañana": range(8, 14), "tarde": range(14, 21), "noche": range(21, 24)}


def _limpio(v):
    return None if v in (None, -9999, "-9999") else v


def _franxa3(x):
    if isinstance(x, list):
        return [_limpio(v) for v in x]
    if isinstance(x, dict):
        return [_limpio(x.get("manha")), _limpio(x.get("tarde")), _limpio(x.get("noite"))]
    return [None, None, None]


def franja_mg(h):
    """Franjas reales de MeteoGalicia: mañana 06-13, tarde 14-20, noche 21-05."""
    if 6 <= h <= 13:
        return 0
    if 14 <= h <= 20:
        return 1
    return 2


def ceo_a_wmo(code):
    return CEO_A_WMO.get(re.sub(r"^2", "1", str(code or "")), 3)


def vento_kmh(code):
    if not isinstance(code, (int, float)):
        return None
    code = int(code)
    if code == 299:
        return 3
    if code == 300:
        return 10
    if 301 <= code <= 308:
        return 12      # flojo, 5-20
    if 309 <= code <= 316:
        return 30      # moderado, 20-40
    if 317 <= code <= 324:
        return 55      # fuerte, 40-70
    if 325 <= code <= 332:
        return 80      # muy fuerte, >70
    return None


def factor_uv(fecha, hora):
    """Copia de mgFactorUV: cos(cenit)^2.6 a la hora y media local."""
    local = dt.datetime(fecha.year, fecha.month, fecha.day, hora, 30, tzinfo=util.MADRID)
    u = local.astimezone(dt.timezone.utc)
    origen = dt.datetime(u.year, 1, 1, tzinfo=dt.timezone.utc) - dt.timedelta(days=1)
    dia = math.floor((u - origen).total_seconds() / 86400)
    g = 2 * math.pi / 365 * (dia - 1 + (u.hour - 12) / 24)
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    eq = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                   - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    ha = ((u.hour * 60 + u.minute) + eq + 4 * config.LON) / 4 - 180
    r = math.pi / 180
    cosz = (math.sin(config.LAT * r) * math.sin(decl)
            + math.cos(config.LAT * r) * math.cos(decl) * math.cos(ha * r))
    return 0.0 if cosz <= 0 else cosz ** 2.6


# ---------------------------------------------------------------- lectura de fuentes
def _mg_diaria(hoy):
    j = util.descargar(MG_DIARIA.format(c=config.CONCELLO), como="json")
    raiz = j.get("predConcello", j) if isinstance(j, dict) else {}
    for d in raiz.get("listaPredDiaConcello") or []:
        if str(d.get("dataPredicion", ""))[:10] == hoy.isoformat():
            return {
                "tMax": _limpio(d.get("tMax")), "tMin": _limpio(d.get("tMin")),
                "pchoiva": _franxa3(d.get("pchoiva")), "ceo": _franxa3(d.get("ceo")),
                "vento": _franxa3(d.get("vento")), "uvMax": _limpio(d.get("uvMax")),
                "nivelAviso": d.get("nivelAviso"),
            }
    return None


def _mg_horaria():
    j = util.descargar(MG_HORARIA.format(c=config.CONCELLO), como="json")
    raiz = j.get("predHoraria", j) if isinstance(j, dict) else {}
    temp, ceo, vento = {}, {}, {}
    for dd in raiz.get("listaPredDiaHoraria") or []:
        for hh in dd.get("listaPredHora") or []:
            clave = str(hh.get("dataPredicion", ""))[:13]
            if not clave:
                continue
            temp[clave] = _limpio(hh.get("tMedia"))
            ceo[clave] = _limpio(hh.get("icoCeo"))
            vento[clave] = _limpio(hh.get("icoVento"))
    return temp, ceo, vento


def _aemet_mm(hoy):
    datos = util.descargar(AEMET_XML.format(c=config.CONCELLO), como="bytes")
    texto = datos.decode("iso-8859-15", "replace")
    texto = re.sub(r"^<\?xml[^>]*\?>", "", texto.strip())
    raiz = ET.fromstring(texto)
    mm = {}
    for dia in raiz.iter("dia"):
        if dia.get("fecha") != hoy.isoformat():
            continue
        for p in dia.findall("precipitacion"):
            per = p.get("periodo") or ""
            if not per.isdigit():
                continue
            v = (p.text or "").strip()
            if v.lower() == "ip":       # inapreciable
                val = 0.05
            else:
                try:
                    val = float(v.replace(",", "."))
                except ValueError:
                    continue
            mm[int(per)] = val
    return mm


def _open_meteo(hoy):
    j = util.descargar(OPEN_METEO.format(lat=config.LAT, lon=config.LON), como="json")
    h = j.get("hourly") or {}
    salida = {}
    for i, t in enumerate(h.get("time") or []):
        if t[:10] != hoy.isoformat():
            continue
        hora = int(t[11:13])

        def v(nombre):
            serie = h.get(nombre)
            return serie[i] if serie and i < len(serie) else None

        uv = v("uv_index_clear_sky")
        if uv is None:
            uv = v("uv_index")
        salida[hora] = {
            "temp": v("temperature_2m"), "lluvia": v("precipitation"),
            "prob": v("precipitation_probability"), "uv": uv,
            "viento": v("windspeed_10m"), "racha": v("windgusts_10m"), "wcode": v("weathercode"),
        }
    return salida


# ---------------------------------------------------------------- horas del día
def obtener_horas(hoy):
    """Devuelve (horas, fuente, avisos_de_fuentes, mg_diaria)."""
    problemas = []
    try:
        om = _open_meteo(hoy)
    except Exception as e:
        om, _ = {}, problemas.append(f"Open-Meteo: {e}")
    try:
        mg = _mg_diaria(hoy)
    except Exception as e:
        mg = None
        problemas.append(f"MeteoGalicia diaria: {e}")

    if not mg:
        horas = []
        for h in range(H0, 24):
            o = om.get(h)
            if not o:
                continue
            horas.append({
                "h": h, "temp": o["temp"], "lluvia": o["lluvia"], "prob": o["prob"],
                "uv": round(o["uv"]) if isinstance(o["uv"], (int, float)) else None,
                "viento": o["viento"], "racha": o["racha"], "wcode": o["wcode"],
            })
        return horas, "Open-Meteo", problemas, None

    try:
        temp_mg, ceo_mg, vento_mg = _mg_horaria()
    except Exception as e:
        temp_mg, ceo_mg, vento_mg = {}, {}, {}
        problemas.append(f"MeteoGalicia horaria: {e}")
    try:
        mm_aemet = _aemet_mm(hoy)
    except Exception as e:
        mm_aemet = {}
        problemas.append(f"AEMET: {e}")

    horas, max_f = [], 0.0
    for h in range(H0, 24):
        cl = f"{hoy.isoformat()}T{h:02d}"
        f = franja_mg(h)
        o = om.get(h, {})
        ceo = ceo_mg.get(cl)
        if ceo is None:
            ceo = mg["ceo"][f]
        wc = ceo_a_wmo(ceo) if ceo is not None else o.get("wcode")
        kmh = vento_kmh(vento_mg.get(cl))
        if kmh is None:
            kmh = vento_kmh(mg["vento"][f])
        fu = factor_uv(hoy, h)
        max_f = max(max_f, fu)
        temp = temp_mg.get(cl)
        if temp is None:
            temp = o.get("temp")
        lluvia = mm_aemet.get(h)
        if lluvia is None:
            lluvia = o.get("lluvia")
        prob = o.get("prob")
        if prob is None:
            prob = mg["pchoiva"][f]
        horas.append({
            "h": h, "temp": temp, "lluvia": lluvia, "prob": prob,
            "prob_franja": mg["pchoiva"][f], "_fuv": fu, "uv": None,
            "viento": kmh, "racha": o.get("racha"), "wcode": wc,
        })
    for o in horas:
        uvmax = mg.get("uvMax")
        o["uv"] = round(uvmax * (o.pop("_fuv") / max_f)) if (isinstance(uvmax, (int, float)) and uvmax > 0 and max_f > 0) else None
    fuente = "MeteoGalicia" + (" · mm AEMET" if mm_aemet else "") + (" · % Open-Meteo" if om else " · % por franjas")
    return horas, fuente, problemas, mg


# ---------------------------------------------------------------- resumen para el guion
def _tramos(horas_marcadas):
    """[13,14,15,18] → [(13,16),(18,19)] (fin no incluido)."""
    tramos = []
    for h in sorted(horas_marcadas):
        if tramos and h == tramos[-1][1]:
            tramos[-1] = (tramos[-1][0], h + 1)
        else:
            tramos.append((h, h + 1))
    return tramos


def _cielo(horas, rango):
    codigos = [o["wcode"] for o in horas if o["h"] in rango and isinstance(o.get("wcode"), (int, float))]
    if not codigos:
        return None
    frecuente = max(set(codigos), key=codigos.count)
    peor = max(codigos, key=lambda c: GRAVEDAD.get(int(c), 3))
    texto = WMO_TEXTO.get(int(frecuente), "nublado")
    if GRAVEDAD.get(int(peor), 0) >= 5 and GRAVEDAD.get(int(frecuente), 0) < 5:
        texto += f", con algún episodio de {WMO_TEXTO.get(int(peor), 'lluvia')}"
    return texto


def resumir(horas, mg, avisos_aemet=None):
    r = {"horas_consideradas": "de las 8 a medianoche"}
    temps = [(o["h"], o["temp"]) for o in horas if isinstance(o.get("temp"), (int, float))]
    if temps:
        hmax, tmax = max(temps, key=lambda x: x[1])
        hmin, tmin = min(temps, key=lambda x: x[1])
        r["temperatura"] = {"maxima": round(tmax), "hora_maxima": hmax,
                            "minima": round(tmin), "hora_minima": hmin,
                            "a_las_8": round(temps[0][1]) if temps[0][0] == 8 else None}
    r["cielo"] = {n: _cielo(horas, rg) for n, rg in FRANJAS.items()}
    lluviosas = [o["h"] for o in horas
                 if (isinstance(o.get("prob"), (int, float)) and o["prob"] >= config.PROB_LLUVIA_FRANJA)
                 or (isinstance(o.get("lluvia"), (int, float)) and o["lluvia"] >= 0.3)]
    franjas = []
    for a, b in _tramos(lluviosas):
        sub = [o for o in horas if a <= o["h"] < b]
        franjas.append({
            "desde": a, "hasta": b,
            "probabilidad_maxima": max((o["prob"] or 0) for o in sub),
            "litros_m2": round(sum((o["lluvia"] or 0) for o in sub), 1),
        })
    probs = [o["prob"] for o in horas if isinstance(o.get("prob"), (int, float))]
    r["lluvia"] = {"franjas_con_lluvia_probable": franjas,
                   "probabilidad_maxima_del_dia": max(probs) if probs else None,
                   "litros_m2_total": round(sum((o["lluvia"] or 0) for o in horas), 1)}
    paseos = {}
    for nombre, (a, b) in config.PASEOS.items():
        sub = [o for o in horas if a <= o["h"] < b]
        if not sub:
            continue
        paseos[nombre] = {
            "de": a, "a": b,
            "probabilidad_lluvia_maxima": max((o["prob"] or 0) for o in sub),
            "litros_m2": round(sum((o["lluvia"] or 0) for o in sub), 1),
            "temperatura": round(sum(o["temp"] for o in sub if o.get("temp") is not None) /
                                 max(1, len([o for o in sub if o.get("temp") is not None]))) if any(o.get("temp") is not None for o in sub) else None,
        }
    r["paseos"] = paseos
    vientos = [(o["h"], o["viento"]) for o in horas if isinstance(o.get("viento"), (int, float))]
    rachas = [(o["h"], o["racha"]) for o in horas if isinstance(o.get("racha"), (int, float))]
    if vientos:
        vmax = max(v for _, v in vientos)
        horas_vmax = [h for h, v in vientos if v == vmax]
        r["viento"] = {"maximo_kmh_aprox": round(vmax),
                       "banda": "calma" if vmax <= 5 else "flojo" if vmax <= 20 else "moderado" if vmax <= 40 else "fuerte" if vmax <= 70 else "muy fuerte",
                       "desde": min(horas_vmax), "hasta": max(horas_vmax) + 1}
    if rachas:
        hr, rmax = max(rachas, key=lambda x: x[1])
        r.setdefault("viento", {})["racha_maxima_kmh"] = round(rmax)
        r["viento"]["hora_racha_maxima"] = hr
    uvs = [(o["h"], o["uv"]) for o in horas if isinstance(o.get("uv"), (int, float))]
    if uvs:
        huv, uvmax = max(uvs, key=lambda x: x[1])
        prot = [h for h, v in uvs if v >= config.UV_PROTECCION]
        r["uv"] = {"maximo": uvmax, "hora_maximo": huv,
                   "proteccion_solar_desde": min(prot) if prot else None,
                   "proteccion_solar_hasta": (max(prot) + 1) if prot else None}
    r["tormenta"] = any(int(o.get("wcode") or 0) in (95, 96, 99) for o in horas)
    r["avisos_aemet"] = avisos_aemet or []
    if mg and mg.get("nivelAviso"):
        r["nivel_aviso_meteogalicia"] = mg["nivelAviso"]
    return r


def numeros_permitidos(r, hoy):
    """Cifras que el bloque del tiempo puede decir (para comprobar que la IA no inventa)."""
    nums = {str(hoy.day), "100"}

    def meter(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            nums.add(str(int(round(v))))
            if isinstance(v, float):
                nums.add(f"{v:.1f}".replace(".", ","))
                nums.add(f"{v:.1f}")
            if 0 <= v <= 24 and float(v).is_integer():
                h = int(v)
                nums.add(str(h % 12 or 12))
        elif isinstance(v, dict):
            for x in v.values():
                meter(x)
        elif isinstance(v, list):
            for x in v:
                meter(x)

    meter(r)
    return nums


def texto_plantilla(r):
    """Versión sin IA del bloque del tiempo (se usa si el guion trae cifras que no cuadran)."""
    t = []
    c = r.get("cielo") or {}
    partes = []
    if c.get("mañana"):
        partes.append(f"por la mañana, {c['mañana']}")
    if c.get("tarde"):
        partes.append(f"por la tarde, {c['tarde']}")
    if c.get("noche") and c.get("noche") != c.get("tarde"):
        partes.append(f"y por la noche, {c['noche']}")
    if partes:
        t.append("El tiempo hoy en A Coruña: " + "; ".join(partes) + ".")
    tp = r.get("temperatura")
    if tp:
        t.append(f"Temperaturas entre {tp['minima']} y {tp['maxima']} grados, con la máxima hacia "
                 f"{util.hora_hablada(tp['hora_maxima'])}.")
    ll = r.get("lluvia") or {}
    fr = ll.get("franjas_con_lluvia_probable") or []
    if not fr:
        t.append("No se espera lluvia.")
    else:
        trozos = [f"de {util.hora_hablada(f['desde'])} a {util.hora_hablada(f['hasta'])}, "
                  f"con hasta un {f['probabilidad_maxima']} por ciento de probabilidad" for f in fr[:3]]
        t.append("Puede llover " + util.lista_hablada(trozos) + ".")
    paseos = r.get("paseos") or {}
    mojados = [n for n, p in paseos.items() if p["probabilidad_lluvia_maxima"] >= config.PROB_LLUVIA_FRANJA]
    if paseos and not mojados:
        t.append("Para los paseos, el de la mañana y el de la noche, no hace falta paraguas.")
    elif mojados:
        t.append("Ojo con el " + util.lista_hablada(mojados) + ": mejor lleva paraguas.")
    v = r.get("viento") or {}
    if v.get("maximo_kmh_aprox", 0) >= 30 or v.get("racha_maxima_kmh", 0) >= 50:
        frase = f"Viento {v.get('banda', 'moderado')}"
        if v.get("racha_maxima_kmh"):
            frase += f", con rachas de hasta {v['racha_maxima_kmh']} kilómetros por hora"
        t.append(frase + ".")
    uv = r.get("uv")
    if uv:
        if uv["maximo"] >= config.UV_PROTECCION and uv["proteccion_solar_desde"] is not None:
            t.append(f"Índice ultravioleta de hasta {uv['maximo']}: conviene protección solar de "
                     f"{util.hora_hablada(uv['proteccion_solar_desde'])} a {util.hora_hablada(uv['proteccion_solar_hasta'])}.")
        elif uv["maximo"] >= 1:
            t.append(f"El índice ultravioleta se queda en {uv['maximo']}: con la gorra es suficiente.")
    for a in (r.get("avisos_aemet") or [])[:3]:
        t.append(f"Atención: aviso {a.get('level', '')} por {a.get('phenomenon', '')}"
                 + (f" {a.get('timeframe')}" if a.get("timeframe") else "") + ".")
    return " ".join(t)


# ---------------------------------------------------------------- versión breve (la que se usa)
PARTES_DIA = (("por la mañana", range(8, 14)), ("por la tarde", range(14, 21)), ("por la noche", range(21, 24)))


def _cuando(partes):
    if len(partes) == 3:
        return "todo el día"
    return util.lista_hablada(partes)


def texto_breve(horas, r):
    """El tiempo en dos o tres frases: cielo y temperaturas, si llueve o no, si hace falta crema."""
    frases = []
    cielo = _cielo(horas, range(8, 21))
    tp = r.get("temperatura")
    if cielo and tp:
        frases.append(f"El tiempo: {cielo}, entre {tp['minima']} y {tp['maxima']} grados.")
    elif tp:
        frases.append(f"El tiempo: entre {tp['minima']} y {tp['maxima']} grados.")
    llueve, quiza = [], []
    for nombre, rango in PARTES_DIA:
        sub = [o for o in horas if o["h"] in rango]
        pmax = max([(o.get("prob") or 0) for o in sub] or [0])
        mm = sum((o.get("lluvia") or 0) for o in sub)
        if pmax >= 50 or mm >= 0.5:
            llueve.append(nombre)
        elif pmax >= 30:
            quiza.append(nombre)
    if llueve:
        frases.append(f"Va a llover {_cuando(llueve)}, así que paraguas."
                      + (f" Y puede caer algo {_cuando(quiza)}." if quiza else ""))
    elif quiza:
        frases.append(f"No se espera mucha lluvia, aunque puede caer algo {_cuando(quiza)}.")
    else:
        frases.append("No va a llover.")
    uv = r.get("uv")
    if uv and uv.get("maximo", 0) >= config.UV_PROTECCION and uv.get("proteccion_solar_desde") is not None:
        a, b = uv["proteccion_solar_desde"], uv["proteccion_solar_hasta"]
        na, nb = util.NUMEROS.get(a % 12 or 12), util.NUMEROS.get(b % 12 or 12)
        frases.append(f"Crema, sí: entre la{'s' if (a % 12 or 12) != 1 else ''} {na} y la{'s' if (b % 12 or 12) != 1 else ''} {nb} pega fuerte el sol.")
    else:
        frases.append("Crema, hoy no hace falta.")
    for a in (r.get("avisos_aemet") or [])[:2]:
        if a.get("phenomenon"):
            frases.append(f"Ojo, que hay aviso {a.get('level', '')} por {a['phenomenon']}.")
    return " ".join(frases)
