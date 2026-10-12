"""Escribe el guion con Gemini (plan gratuito) y lo revisa antes de ponerle voz.

- La agenda NO pasa por el guionista: se lee con plantilla fija (agenda.py).
- El tiempo lo redacta Gemini con datos ya masticados; si cuela alguna cifra que no está
  en los datos, ese bloque se sustituye por la versión de plantilla (tiempo.py).
- Si Gemini no responde, se monta un boletín sencillo sin IA para que el pódcast llegue igual.
"""
import json
import os
import re
import time

import requests

from . import config, tiempo, util

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
BLOQUES = ["apertura", "tiempo", "portada", "interes", "local", "cierre"]

ESQUEMA = {
    "type": "OBJECT",
    "properties": {
        "segmentos": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "bloque": {"type": "STRING", "enum": BLOQUES},
                    "voz": {"type": "STRING", "enum": ["A", "B"]},
                    "texto": {"type": "STRING"},
                },
                "required": ["bloque", "voz", "texto"],
            },
        }
    },
    "required": ["segmentos"],
}


def instrucciones():
    a = config.LOCUTORES["A"]["nombre"]
    b = config.LOCUTORES["B"]["nombre"]
    return f"""Eres el guionista de «El Noticiario de Iago», un pódcast privado de unos 11 minutos que escucha una sola persona, Iago, mientras pasea a primera hora por A Coruña.

FORMATO
- Dos locutores que se turnan por bloques, como en un informativo de radio: A ({a}) y B ({b}).
- Orden de bloques: apertura (A) → tiempo (B) → portada → interes → local → cierre. Entre la apertura y el tiempo el programa inserta la agenda del día, que lee A y que NO escribes tú.
- En portada, interes y local alterna las voces: un bloque puede llevarlo una sola voz o repartirse en dos segmentos seguidos (A y B). Cuando cambia la voz, una transición breve y natural (a veces con el nombre del compañero), sin repetir siempre la misma fórmula.
- apertura: 2 o 3 frases. Saluda a Iago por su nombre, di el día de la semana y la fecha, y termina dando paso a su agenda («empezamos por tu día» o algo parecido).
- tiempo: empieza enlazando con la agenda («Y el tiempo…» o similar).
- cierre: 2 o 3 frases. Despedida breve y amable, sin moralejas.

ESTILO
- Radio matinal española de calidad: frases cortas y claras, ritmo ágil, cercano pero profesional.
- Nada de exageraciones, sensacionalismo, chistes forzados ni muletillas («sin más dilación», «abróchate el cinturón», «¡vamos allá!»). Nada de «queridos oyentes»: le hablas a una sola persona.
- Escribe para el oído: sin listas, sin paréntesis, sin enlaces, sin siglas sin explicar la primera vez, cifras redondeadas. Horas como se dicen: «a las 4 de la tarde».
- Las noticias que estén en gallego, cuéntalas en castellano.

CONTENIDO
- Usa SOLO la información que te paso. No inventes datos, nombres, cifras, fechas ni declaraciones. Puedes añadir contexto general muy conocido y prudente, nunca datos concretos que no estén en los textos.
- Elige las 2 o 3 noticias más importantes del día (sobre todo de la portada) y cuéntalas con contexto: qué ha pasado, por qué importa y qué viene ahora (de 3 a 6 frases). El resto, en 1 o 2 frases.
- interes: una noticia por categoría (ciencia, tecnología e IA, economía, investigación divulgativa, salud y longevidad); di de qué va cada una con naturalidad. Si hay alertas sanitarias, cierra el bloque con ellas en una o dos frases claras; si no hay, no hables de alertas.
- local: A Coruña y Galicia. Omite las noticias sobre el tiempo (ya hay bloque del tiempo).
- Si dos noticias cuentan lo mismo, cuéntalo una sola vez. Si una sección viene vacía, sáltala sin comentarlo.
- Real Madrid: NUNCA digas resultados, marcadores, goles ni quién ganó, aunque aparezcan en alguna noticia: Iago ve los resúmenes después y no quiere spoilers. Si una noticia trata del resultado de un partido del Madrid, sáltala. Si en los datos «madrid» pone que jugó, en el cierre di solo que jugó (y contra quién, si viene el rival) y que tiene el resumen en el noticiario.

TIEMPO (bloque «tiempo»)
- Usa SOLO los datos del apartado «tiempo» y escribe sus cifras con dígitos («22 grados», «a las 4 de la tarde», «un 60 por ciento»). No digas ninguna cifra que no esté en esos datos.
- Cuenta: cómo estará el cielo por la mañana, la tarde y la noche; la máxima y la mínima con su hora aproximada; las franjas en las que puede llover y cómo pinta para el paseo de la mañana y el de la noche; el viento solo si es moderado o más, o si hay rachas de 50 o más; el índice ultravioleta máximo y entre qué horas conviene protección solar (si el máximo es menor de 3, basta con decir que no hace falta); y los avisos de AEMET si los hay.
- Entre 120 y 200 palabras.

LONGITUD
- En total, entre {config.PALABRAS_MIN} y {config.PALABRAS_MAX} palabras (la agenda no cuenta). Reparto orientativo: apertura 40, tiempo 160, portada 500, interes 430, local 300, cierre 50.

SALIDA
- Solo el JSON con la lista «segmentos». Cada segmento: «bloque», «voz» (A o B) y «texto» (exactamente lo que se va a leer)."""


def _datos_para_guionista(hoy_dt, noticias, resumen_tiempo):
    def items(lista):
        return [{"titulo": it["titulo"], "fuente": it.get("fuente", ""), "categoria": it.get("categoria", ""),
                 "texto": util.quitar_url(it.get("texto", ""))[:config.TEXTO_MAX_NOTICIA]}
                for it in (lista or [])]
    return {
        "fecha": util.fecha_larga(hoy_dt) + f" de {hoy_dt.year}",
        "locutores": {k: v["nombre"] for k, v in config.LOCUTORES.items()},
        "tiempo": resumen_tiempo,
        "portada": items(noticias.get("portada")),
        "interes": items(noticias.get("interes")),
        "local": items(noticias.get("local")),
        "alertas_sanitarias": noticias.get("alertas_sanitarias") or [],
        "avisos_aemet": noticias.get("avisos_aemet") or [],
        "madrid": noticias.get("madrid") or {"jugo": False},
    }


class ErrorApi(Exception):
    def __init__(self, codigo, texto):
        super().__init__(f"HTTP {codigo}: {texto[:400]}")
        self.codigo = codigo
        self.texto = texto


def _llamar(modelo, sistema, usuario, con_esquema=True):
    clave = os.environ.get("GEMINI_API_KEY", "")
    cfg = {"temperature": 0.7, "responseMimeType": "application/json", "maxOutputTokens": 24000}
    if con_esquema:
        cfg["responseSchema"] = ESQUEMA
    cuerpo = {
        "systemInstruction": {"parts": [{"text": sistema}]},
        "contents": [{"role": "user", "parts": [{"text": usuario}]}],
        "generationConfig": cfg,
    }
    r = requests.post(URL.format(modelo=modelo), json=cuerpo, timeout=240,
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
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    j = json.loads(texto)
    segs = j.get("segmentos") if isinstance(j, dict) else j
    limpios = []
    for s in segs or []:
        bloque = str(s.get("bloque", "")).strip().lower()
        voz = str(s.get("voz", "A")).strip().upper()[:1]
        t = re.sub(r"\s+", " ", str(s.get("texto", ""))).strip()
        if bloque not in BLOQUES or not t:
            continue
        limpios.append({"bloque": bloque, "voz": voz if voz in ("A", "B") else "A", "texto": t})
    if len(limpios) < 3:
        raise ValueError("el guion no trae segmentos suficientes")
    return limpios


def _espera_429(texto):
    m = re.search(r'"retryDelay"\s*:\s*"(\d+)', texto or "")
    return min(70, int(m.group(1)) + 2) if m else 25


def _pedir_guion(sistema, usuario):
    errores = []
    for modelo in config.MODELOS_TEXTO:
        for intento in range(2):
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
                if e.codigo == 429 and intento == 0:
                    time.sleep(_espera_429(e.texto))
                    continue
                if e.codigo >= 500 and intento == 0:
                    time.sleep(8)
                    continue
                break
            except Exception as e:  # JSON roto, etc.
                errores.append(f"{modelo}: {type(e).__name__}: {e}")
                if intento == 0:
                    continue
                break
    return None, None, errores


RE_MARCADOR = re.compile(r"\b\d{1,2}\s*(?:-|–|a)\s*\d{1,2}\b")


def _sin_spoilers(texto):
    frases = re.split(r"(?<=[.!?…])\s+", texto)
    buenas = [f for f in frases if not ("madrid" in f.lower() and RE_MARCADOR.search(f))]
    return " ".join(buenas).strip()


def _tiempo_valido(texto, permitidos):
    for n in re.findall(r"\d+(?:[.,]\d+)?", texto):
        if n not in permitidos and n.replace(",", ".") not in permitidos and str(int(float(n.replace(",", ".")))) not in permitidos:
            return False, n
    return True, None


def guion_sin_ia(hoy_dt, noticias, resumen_tiempo):
    """Boletín de reserva, sin Gemini: titulares con su primera frase."""
    def primera(t):
        f = re.split(r"(?<=[.!?])\s+", t or "")
        return f[0] if f and len(f[0]) > 30 else (t or "")[:240]

    def bloque(nombre, voz, intro, lista, maximo):
        if not lista:
            return []
        trozos = [intro] + [f"{it['titulo']}. {primera(it.get('texto', ''))}" for it in lista[:maximo]]
        return [{"bloque": nombre, "voz": voz, "texto": " ".join(trozos)}]

    segs = [{"bloque": "apertura", "voz": "A",
             "texto": f"Buenos días, Iago. Es {util.fecha_larga(hoy_dt)}. Hoy va un boletín más breve de lo habitual. Empezamos por tu día."},
            {"bloque": "tiempo", "voz": "B", "texto": tiempo.texto_plantilla(resumen_tiempo)}]
    segs += bloque("portada", "A", "Vamos con la portada.", noticias.get("portada"), 6)
    segs += bloque("interes", "B", "Ahora, las noticias de interés.", noticias.get("interes"), 5)
    segs += bloque("local", "A", "Y en Coruña y Galicia.", noticias.get("local"), 5)
    segs.append({"bloque": "cierre", "voz": "B", "texto": "Esto ha sido todo por hoy. Que tengas un buen día."})
    return segs


def escribir(hoy_dt, noticias, resumen_tiempo, texto_agenda):
    """Devuelve (segmentos, info). Los segmentos ya incluyen la agenda tras la apertura."""
    info = {"modelo": None, "avisos": []}
    datos = _datos_para_guionista(hoy_dt, noticias, resumen_tiempo)
    usuario = "DATOS DE HOY (JSON):\n" + json.dumps(datos, ensure_ascii=False)
    sistema = instrucciones()
    segs, modelo, errores = _pedir_guion(sistema, usuario)
    if errores:
        info["avisos"] += errores
    if segs:
        total = sum(util.palabras(s["texto"]) for s in segs)
        if total < config.PALABRAS_MIN * 0.75 or total > config.PALABRAS_MAX * 1.25:
            util.log(f"Guion con {total} palabras: pido que lo ajuste")
            usuario2 = usuario + (f"\n\nOJO: tu versión anterior tenía {total} palabras. Ajusta el guion a "
                                  f"entre {config.PALABRAS_MIN} y {config.PALABRAS_MAX} palabras.")
            segs2, modelo2, err2 = _pedir_guion(sistema, usuario2)
            info["avisos"] += err2
            if segs2:
                segs, modelo = segs2, modelo2
        info["modelo"] = modelo
    else:
        info["avisos"].append("Gemini no respondió: boletín de reserva sin IA.")
        info["modelo"] = "plantilla (sin IA)"
        segs = guion_sin_ia(hoy_dt, noticias, resumen_tiempo)

    # orden canónico de bloques y voces razonables
    segs.sort(key=lambda s: BLOQUES.index(s["bloque"]))
    if segs and segs[0]["bloque"] != "apertura":
        segs.insert(0, {"bloque": "apertura", "voz": "A",
                        "texto": f"Buenos días, Iago. Es {util.fecha_larga(hoy_dt)}. Empezamos por tu día."})

    # el tiempo: ninguna cifra que no esté en los datos
    permitidos = tiempo.numeros_permitidos(resumen_tiempo, hoy_dt.date())
    for s in segs:
        if s["bloque"] == "tiempo":
            ok, cifra = _tiempo_valido(s["texto"], permitidos)
            if not ok:
                info["avisos"].append(f"El tiempo traía una cifra que no está en los datos ({cifra}): uso la plantilla.")
                s["texto"] = "Y el tiempo. " + tiempo.texto_plantilla(resumen_tiempo)
    if not any(s["bloque"] == "tiempo" for s in segs):
        segs.insert(1, {"bloque": "tiempo", "voz": "B", "texto": tiempo.texto_plantilla(resumen_tiempo)})

    # sin spoilers del Madrid, por si acaso
    for s in segs:
        s["texto"] = _sin_spoilers(s["texto"])
    segs = [s for s in segs if s["texto"]]

    # la agenda va justo después de la apertura, con la voz de la apertura
    i = next(i for i, s in enumerate(segs) if s["bloque"] == "apertura")
    segs.insert(i + 1, {"bloque": "agenda", "voz": segs[i]["voz"], "texto": texto_agenda})
    info["palabras"] = sum(util.palabras(s["texto"]) for s in segs)
    return segs, info


def a_markdown(segs, info, hoy_dt, extra=""):
    nombres = {k: v["nombre"] for k, v in config.LOCUTORES.items()}
    lineas = [f"# Noticiario de Iago · {util.fecha_larga(hoy_dt)}", "",
              f"_Guion: {info.get('modelo')} · {info.get('palabras', 0)} palabras_{extra}", ""]
    actual = None
    for s in segs:
        if s["bloque"] != actual:
            lineas += ["", f"## {s['bloque'].capitalize()}", ""]
            actual = s["bloque"]
        lineas.append(f"**{nombres.get(s['voz'], s['voz'])}:** {s['texto']}")
        lineas.append("")
    if info.get("avisos"):
        lineas += ["", "---", "", "### Avisos de la generación", ""] + [f"- {a}" for a in info["avisos"]]
    return "\n".join(lineas)
