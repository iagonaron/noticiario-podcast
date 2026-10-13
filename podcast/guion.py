"""Escribe el guion con Gemini (plan gratuito): un diálogo ágil y constante entre dos voces, sin
saludos ni nombres, que va directo a las noticias y las cuenta fácil y con desenfado.

Orden del programa (main.py lo monta):
  apertura y lo rápido (plantillas fijas, sin IA): «Hoy es…», cumpleaños y festivos, agenda, tiempo
  → titulares (El País Exprés) → local (3 noticias) → interes (ciencia, salud, economía…)
  → distinto (el momento Distinto Básico) → cierre (plantilla)
Cada turno lleva el número de la noticia a la que pertenece: entre una noticia y la siguiente
el montaje sube la música unos segundos.
Si Gemini no responde, se monta un boletín sencillo sin IA para que el pódcast llegue igual.
"""
import json
import os
import re
import time

import requests

from . import config, util

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
BLOQUES = ["titulares", "local", "interes", "distinto"]          # lo que escribe la IA
ORDEN = ["apertura", "rapido", "titulares", "local", "interes", "distinto", "cierre"]
TITULOS = {"apertura": "Hoy", "rapido": "Lo rápido del día", "titulares": "Titulares",
           "local": "Coruña y Galicia", "interes": "Ciencia, salud y economía",
           "distinto": "Momento Distinto Básico", "cierre": "Cierre"}
_NOMBRES = sorted({n for v in config.LOCUTORES.values() for n in (v["nombre"], util.sin_tildes(v["nombre"]))} | {"A", "B"})
RE_NOMBRE_DELANTE = re.compile(r"^(?:" + "|".join(map(re.escape, _NOMBRES)) + r")\s*:\s+")

ESQUEMA = {
    "type": "OBJECT",
    "properties": {
        "segmentos": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "bloque": {"type": "STRING", "enum": BLOQUES},
                    "noticia": {"type": "INTEGER"},
                    "voz": {"type": "STRING", "enum": ["A", "B"]},
                    "texto": {"type": "STRING"},
                },
                "required": ["bloque", "noticia", "voz", "texto"],
            },
        }
    },
    "required": ["segmentos"],
}


def _objetivo(con_plan):
    """(mínimo, máximo) de palabras de lo que escribe la IA."""
    menos = 0 if con_plan else config.REPARTO["distinto"]
    return config.PALABRAS_MIN - menos, config.PALABRAS_MAX - menos


def instrucciones(n_noticias, con_plan):
    minimo, maximo = _objetivo(con_plan)
    reparto = (f"titulares {config.REPARTO['titulares']}, local {config.REPARTO['local']}, "
               f"interes {config.REPARTO['interes']}" + (f", distinto {config.REPARTO['distinto']}" if con_plan else ""))
    plan = """
MOMENTO DISTINTO BÁSICO (bloque «distinto», el último)
- Empieza exactamente con: «Y para terminar, el momento Distinto Básico.»
- Es la propuesta de plan de hoy para Iago y su pareja, Laura (viene en «distinto_basico»). Contadla entre los dos, en diálogo, en 4 a 6 turnos (unas 170 palabras): qué es, explicado a quien no lo conoce; cuándo y dónde; cuánto cuesta; si hay que reservar y con cuánta antelación; y dónde comer vegano cerca. Aquí sí podéis decir por qué les puede gustar.
- Usa SOLO lo que viene en «distinto_basico»: ni fechas, ni horas, ni precios, ni sitios inventados. Si un dato no viene, no lo digas. Las direcciones web no se leen.
- Si en «visma» pone true, podéis decir que Visma, su perra, también puede ir.
""" if con_plan else ""
    return f"""Escribes el guion de un pódcast diario de noticias que escucha una sola persona, Iago, por la mañana en A Coruña.

FORMATO: DIÁLOGO CONSTANTE ENTRE DOS VOCES
- Dos presentadores, voz A y voz B, que se reparten cada noticia en diálogo, al estilo de los pódcast de NotebookLM. Le hablan a Iago de tú.
- NO se presentan, NO se saludan, NO dicen sus nombres ni el de Iago y NO se despiden: el programa ya tiene su entrada y su salida. Empezad directamente con la primera noticia.
- Diálogo SIEMPRE: cada noticia la cuentan entre los dos, alternando la voz en cada turno (A, B, A, B…). Nunca dos turnos seguidos de la misma voz, nunca más de 45 palabras en un turno y ninguna noticia contada por una voz sola.
- Uno cuenta y el otro pregunta lo que se preguntaría cualquiera («¿y eso en qué me afecta?», «a ver, explícame eso»), reacciona («¡no me digas!», «ojo con esto»), resume o pone un ejemplo. Se van turnando ese papel.
- Español de España, coloquial y natural. Desenfadado, con humor ligero cuando cuadre, sin pasarse: nada de chistes malos, risas escritas, gritos ni exageraciones.
- Que se entienda TODO a la primera: palabras sencillas, comparaciones con la vida diaria, cifras redondeadas («casi el doble», «unos ciento sesenta mil»), siglas explicadas, nada de jerga.
- Escribe las cifras con letras, tal como se dicen («dos mil veintiséis», «el veinticinco por ciento»).
- Escribe solo lo que se dice: sin acotaciones, sin nombres delante, sin paréntesis, sin enlaces, sin listas, sin emojis.
- No des por hecho los gustos, costumbres o planes de Iago ni le digas qué le va a interesar{" (salvo en el momento Distinto Básico, que es para eso)" if con_plan else ""}. Fuera de ese momento, nada de perros, paseos ni desayunos.

BLOQUES, EN ESTE ORDEN (antes, el programa ya dice la fecha, los cumpleaños, la agenda y el tiempo: no hables de eso)
1. titulares: las noticias de «titulares» (la portada de El País Exprés). Empieza directamente con la primera, sin preámbulos.
2. local: las noticias de «local» (A Coruña y Galicia), con un enlace muy corto al empezar («Y aquí, en Coruña…»).
3. interes: las de «interes» (ciencia, salud, economía, tecnología…). Si hay alertas sanitarias, se dicen claras al final de este bloque; si no hay, ni se mencionan.{chr(10) + "4. distinto: el momento Distinto Básico." if con_plan else ""}
Entre una noticia y la siguiente sonará una ráfaga de música, así que no hacen falta frases de enlace del tipo «cambiando de tema».

QUÉ CONTAR
- Cuenta TODAS las noticias que te paso ({n_noticias} en total), salvo las repetidas y las que sean solo del tiempo.
- Para cada noticia: qué ha pasado, explicado fácil; por qué importa o en qué le afecta a una persona normal; y, si lo hay, un detalle curioso o qué va a pasar ahora.
- Las 2 o 3 más importantes del día, con algo más de calma (4 a 6 turnos). El resto, resumidas (2 o 3 turnos).
- Usa SOLO la información que te paso. No inventes datos, nombres, cifras, fechas ni declaraciones.
- Las noticias en gallego, cuéntalas en castellano.
- Deportes: NUNCA digas resultados, marcadores, goles ni quién ganó.
{plan}
NUMERACIÓN
- Cada turno lleva «noticia»: el número de la noticia que se está contando, empezando por 1 y siguiendo en orden por todo el programa (los titulares 1, 2, 3…, y local e interes siguen la cuenta). Todos los turnos de una misma noticia llevan el mismo número.{" El momento Distinto Básico es la última." if con_plan else ""}

LONGITUD
- Entre {minimo} y {maximo} palabras en total: el programa entero dura unos 12 minutos. Reparto orientativo: {reparto}. Mejor quedarse algo corto que largo.

SALIDA
- Solo el JSON con «segmentos»: cada turno con «bloque», «noticia», «voz» (A o B) y «texto» (exactamente lo que se dice)."""


def _datos_para_guionista(hoy_dt, noticias, plan=None):
    def items(lista):
        return [{"titulo": it["titulo"], "fuente": it.get("fuente", ""), "categoria": it.get("categoria", ""),
                 "texto": util.quitar_url(it.get("texto", ""))[:config.TEXTO_MAX_NOTICIA]}
                for it in (lista or [])]
    datos = {
        "fecha": util.fecha_larga(hoy_dt) + f" de {hoy_dt.year}",
        "titulares": items(noticias.get("portada")),
        "local": items((noticias.get("local") or [])[:config.LOCAL_MAX]),
        "interes": items(noticias.get("interes")),
        "alertas_sanitarias": noticias.get("alertas_sanitarias") or [],
    }
    if plan:
        datos["distinto_basico"] = {k: v for k, v in plan.items() if k not in ("fuentes", "fuente")}
    return datos


class ErrorApi(Exception):
    def __init__(self, codigo, texto):
        m = re.search(r'"message"\s*:\s*"([^"]{0,160})', texto or "")
        super().__init__(f"HTTP {codigo}: {m.group(1) if m else (texto or '')[:160]}")
        self.codigo = codigo
        self.texto = texto


def _llamar(modelo, sistema, usuario, con_esquema=True):
    clave = os.environ.get("GEMINI_API_KEY", "")
    cfg = {"temperature": 0.85, "responseMimeType": "application/json", "maxOutputTokens": 32000}
    if con_esquema:
        cfg["responseSchema"] = ESQUEMA
    cuerpo = {
        "systemInstruction": {"parts": [{"text": sistema}]},
        "contents": [{"role": "user", "parts": [{"text": usuario}]}],
        "generationConfig": cfg,
    }
    r = requests.post(URL.format(modelo=modelo), json=cuerpo, timeout=420,
                      headers={"x-goog-api-key": clave, "Content-Type": "application/json"})
    if r.status_code != 200:
        raise ErrorApi(r.status_code, r.text)
    j = r.json()
    partes = (((j.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
    texto = "".join(p.get("text", "") for p in partes if not p.get("thought"))
    if not texto.strip():
        raise ErrorApi(200, "respuesta vacía: " + json.dumps(j)[:300])
    return texto


def _parsear(texto):
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip())
    j = json.loads(texto)
    segs = j.get("segmentos") if isinstance(j, dict) else j
    limpios, ultima = [], 1
    for s in segs or []:
        bloque = str(s.get("bloque", "")).strip().lower()
        if bloque == "portada":
            bloque = "titulares"
        voz = str(s.get("voz", "A")).strip().upper()[:1]
        t = re.sub(r"\s+", " ", str(s.get("texto", ""))).strip()
        t = RE_NOMBRE_DELANTE.sub("", t)          # por si se cuela «Lucía:» delante del texto
        if bloque not in BLOQUES or not t:
            continue
        try:
            ultima = int(s.get("noticia", ultima))
        except (TypeError, ValueError):
            pass
        limpios.append({"bloque": bloque, "noticia": ultima, "voz": voz if voz in ("A", "B") else "A", "texto": t})
    if len(limpios) < 6:
        raise ValueError("el guion no trae turnos suficientes")
    return limpios


def _espera_429(texto):
    m = re.search(r'"retryDelay"\s*:\s*"(\d+)', texto or "")
    return min(70, int(m.group(1)) + 2) if m else 25


def _pedir_guion(sistema, usuario):
    errores, t0 = [], time.time()
    for n_modelo, modelo in enumerate(config.MODELOS_TEXTO):
        intentos = 3 if n_modelo == 0 else 2       # con el mejor modelo, algo más de paciencia
        for intento in range(intentos):
            if time.time() - t0 > 900:          # 15 minutos como mucho: después, boletín sin IA
                errores.append("se acabó el tiempo para el guion")
                return None, None, errores
            try:
                try:
                    texto = _llamar(modelo, sistema, usuario, con_esquema=True)
                except ErrorApi as e:
                    if e.codigo == 400 and "schema" in e.texto.lower():
                        texto = _llamar(modelo, sistema, usuario, con_esquema=False)
                    else:
                        raise
                return _parsear(texto), modelo, errores
            except ErrorApi as e:
                errores.append(f"{modelo}: {e}")
                if e.codigo == 429 and intento < intentos - 1 and "per day" not in e.texto.lower() \
                        and "perday" not in e.texto.lower():
                    time.sleep(_espera_429(e.texto))
                    continue
                if e.codigo >= 500 and intento < intentos - 1:
                    time.sleep(15 * (intento + 1))       # saturado: 15 s y luego 30 s
                    continue
                break
            except requests.Timeout:
                errores.append(f"{modelo}: no respondió a tiempo")
                break                          # siguiente modelo
            except Exception as e:  # JSON roto, etc.
                errores.append(f"{modelo}: {type(e).__name__}: {str(e)[:160]}")
                if intento == 0:
                    continue
                break
    return None, None, errores


RE_MARCADOR = re.compile(r"\b\d{1,2}\s*(?:-|–|a)\s*\d{1,2}\b")


def _sin_spoilers(texto):
    frases = re.split(r"(?<=[.!?…])\s+", texto)
    buenas = [f for f in frases if not ("madrid" in f.lower() and RE_MARCADOR.search(f))]
    return " ".join(buenas).strip()


def _ordenar_y_numerar(segs):
    """Bloques en su orden; dentro de cada bloque, el orden del guionista. Números de noticia
    consecutivos (1, 2, 3…) para que el montaje sepa dónde empieza cada una."""
    segs = sorted(segs, key=lambda s: BLOQUES.index(s["bloque"]))
    n, previa = 0, None
    for s in segs:
        clave = (s["bloque"], s["noticia"])
        if clave != previa:
            n += 1
            previa = clave
        s["noticia"] = n
    return segs


def _unir_seguidos(segs):
    """Si el guionista pone dos turnos seguidos de la misma voz en la misma noticia, se unen
    (y el aviso queda en el diagnóstico)."""
    salida, unidos = [], 0
    for s in segs:
        p = salida[-1] if salida else None
        if p and p["voz"] == s["voz"] and p["noticia"] == s["noticia"] and p["bloque"] == s["bloque"]:
            p["texto"] = p["texto"] + " " + s["texto"]
            unidos += 1
        else:
            salida.append(dict(s))
    return salida, unidos


def guion_sin_ia(hoy_dt, noticias):
    """Boletín de reserva, sin Gemini: cada noticia, entre las dos voces (título y primera frase)."""
    def frases(t):
        return [f for f in re.split(r"(?<=[.!?])\s+", t or "") if len(f) > 25]

    segs, n = [], 0
    for bloque, clave in (("titulares", "portada"), ("local", "local"), ("interes", "interes")):
        lista = noticias.get(clave) or []
        if bloque == "local":
            lista = lista[:config.LOCAL_MAX]
        for it in lista:
            n += 1
            f = frases(util.quitar_url(it.get("texto", "")))
            segs.append({"bloque": bloque, "noticia": n, "voz": "A", "texto": f"{it['titulo']}."})
            if f:
                segs.append({"bloque": bloque, "noticia": n, "voz": "B", "texto": " ".join(f[:2])[:400]})
    return segs


def apertura(hoy_dt):
    return [{"bloque": "apertura", "noticia": 0, "voz": "A", "texto": f"Hoy es {util.fecha_larga(hoy_dt)}."}]


def cierre(ultima_voz="B"):
    a = "A" if ultima_voz == "B" else "B"
    b = "B" if a == "A" else "A"
    return [{"bloque": "cierre", "noticia": 999, "voz": a, "texto": "Y esto ha sido todo por hoy."},
            {"bloque": "cierre", "noticia": 999, "voz": b, "texto": "¡Hasta mañana!"}]


def escribir(hoy_dt, noticias, plan=None):
    """Devuelve (segmentos, info) de la parte que escribe la IA: titulares, local, interés y,
    si hay propuesta, el momento Distinto Básico."""
    info = {"modelo": None, "avisos": []}
    datos = _datos_para_guionista(hoy_dt, noticias, plan)
    n = sum(len(datos[k]) for k in ("titulares", "interes", "local"))
    usuario = "DATOS DE HOY (JSON):\n" + json.dumps(datos, ensure_ascii=False)
    sistema = instrucciones(n, bool(plan))
    segs, modelo, errores = _pedir_guion(sistema, usuario)
    info["avisos"] += errores
    if segs:
        total = sum(util.palabras(s["texto"]) for s in segs)
        minimo, maximo = _objetivo(bool(plan))
        if total < minimo * 0.8 or total > maximo * 1.2:
            util.log(f"Guion con {total} palabras: pido que lo ajuste")
            usuario2 = usuario + (f"\n\nOJO: tu versión anterior tenía {total} palabras. Ajusta el guion a "
                                  f"entre {minimo} y {maximo} palabras.")
            segs2, modelo2, err2 = _pedir_guion(sistema, usuario2)
            info["avisos"] += err2
            if segs2:
                segs, modelo = segs2, modelo2
        info["modelo"] = modelo
    else:
        info["avisos"].append("Gemini no respondió: boletín de reserva sin IA.")
        info["modelo"] = "plantilla (sin IA)"
        segs = guion_sin_ia(hoy_dt, noticias)

    for s in segs:
        s["texto"] = _sin_spoilers(s["texto"])
    segs = [s for s in segs if s["texto"]]
    segs = _ordenar_y_numerar(segs)
    segs, unidos = _unir_seguidos(segs)
    largos = sum(1 for s in segs if util.palabras(s["texto"]) > 60)
    info["dialogo"] = f"{len(segs)} turnos · {unidos} turnos seguidos de la misma voz unidos · {largos} turnos de más de 60 palabras"
    info["palabras"] = sum(util.palabras(s["texto"]) for s in segs)
    return segs, info


def a_markdown(segs, info, hoy_dt, extra=""):
    nombres = {k: v["nombre"] for k, v in config.LOCUTORES.items()}
    lineas = [f"# Noticiario de Iago · {util.fecha_larga(hoy_dt)}", "",
              f"_Guion: {info.get('modelo')} · {info.get('palabras', 0)} palabras_{extra}", ""]
    actual = None
    for s in segs:
        if s["bloque"] != actual:
            lineas += ["", f"## {TITULOS.get(s['bloque'], s['bloque'].capitalize())}", ""]
            actual = s["bloque"]
        lineas.append(f"**{nombres.get(s['voz'], s['voz'])}:** {s['texto']}")
        lineas.append("")
    if info.get("plan_fuentes"):
        lineas += ["", "---", "", "### Fuentes del momento Distinto Básico", ""] + [f"- {u}" for u in info["plan_fuentes"]]
    if info.get("avisos"):
        lineas += ["", "---", "", "### Avisos de la generación", ""] + [f"- {a}" for a in info["avisos"]]
    return "\n".join(lineas)
