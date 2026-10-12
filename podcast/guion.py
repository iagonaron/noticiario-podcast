"""Escribe el guion de las noticias con Gemini (plan gratuito): una conversación entre dos
locutores, al estilo de los pódcast de NotebookLM, desenfadada y fácil de seguir.

- Lo rápido del principio (cumpleaños, festivos, agenda y tiempo) NO pasa por el guionista:
  se lee con plantillas fijas (main.py), para que no se pueda equivocar ni una hora.
- Si Gemini no responde, se monta un boletín sencillo sin IA para que el pódcast llegue igual.
"""
import json
import os
import re
import time

import requests

from . import config, util

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
BLOQUES = ["apertura", "portada", "interes", "local", "cierre"]
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
                    "voz": {"type": "STRING", "enum": ["A", "B"]},
                    "texto": {"type": "STRING"},
                },
                "required": ["bloque", "voz", "texto"],
            },
        }
    },
    "required": ["segmentos"],
}


def instrucciones(n_noticias):
    a = config.LOCUTORES["A"]["nombre"]
    b = config.LOCUTORES["B"]["nombre"]
    return f"""Escribes el guion de «El Noticiario de Iago», un pódcast diario y privado que escucha una sola persona, Iago, mientras pasea a su perra a primera hora por A Coruña.

FORMATO: UNA CONVERSACIÓN, NO UN TELEDIARIO
- Es una charla entre dos presentadores, {a} (voz A) y {b} (voz B), al estilo de los pódcast de NotebookLM: se hablan entre ellos y le cuentan las noticias a Iago, al que tratan de tú.
- Turnos cortos y vivos: casi siempre de 1 a 3 frases. Nunca más de 70 palabras seguidas de la misma voz. Alternan constantemente.
- Uno cuenta la noticia y el otro hace las preguntas que se haría cualquiera («¿y eso en qué me afecta?», «a ver, explícame eso»), reacciona («¡no me digas!», «ojo con esto»), resume o pone un ejemplo. Van turnándose ese papel.
- Español de España, coloquial y natural, de tú. Desenfadado, con humor ligero cuando cuadre, pero sin pasarse: nada de chistes malos, risas escritas, gritos ni exageraciones.
- Que se entienda TODO a la primera: palabras sencillas, comparaciones con la vida diaria, cifras redondeadas («casi el doble», «unos 160.000»), siglas explicadas, nada de jerga. Si algo es técnico, se explica como a un amigo.
- Escribe solo lo que se dice: sin acotaciones, sin nombres delante, sin paréntesis, sin enlaces, sin listas, sin emojis.
- No des por hecho los gustos, costumbres o lo que come o hace Iago, ni le digas qué le va a interesar («esto para tus desayunos», «apúntatelo para luego»): cuenta la noticia y que él saque sus conclusiones.
- El paseo y la perra, como mucho una vez y solo en el saludo.

BLOQUES, EN ESTE ORDEN
1. apertura: 2 a 4 turnos muy cortos. Saludan a Iago y entre ellos, con el día de la semana y la fecha, y dan paso a «lo rápido del día». Justo después, el programa pone sin ti los cumpleaños, festivos, agenda y tiempo, así que NO hables de eso.
2. portada: empieza con un enlace del tipo «Y ahora sí, las noticias». Las de la portada de El País Exprés.
3. interes: ciencia, tecnología e IA, economía, investigación y salud y longevidad. Si hay alertas sanitarias, se dicen claras al final de este bloque; si no hay, ni se mencionan.
4. local: A Coruña y Galicia.
5. cierre: 2 a 4 turnos. Si en «madrid» pone que jugó, dicen solo que jugó (contra quién, si viene; cuándo, solo si viene «cuando», y si no, sin decir ni «anoche» ni «ayer») y que tiene el resumen en el noticiario. Despedida breve y con buen rollo.

QUÉ CONTAR
- Cuenta TODAS las noticias que te paso ({n_noticias} en total), salvo las repetidas, las que sean solo del tiempo y las de resultados del Madrid.
- Para cada noticia: qué ha pasado, explicado fácil; por qué importa o en qué le afecta a una persona normal; y, si lo hay, un detalle curioso o qué va a pasar ahora.
- Las 3 o 4 más importantes del día, con más calma (de 6 a 10 turnos). El resto, más rápidas (de 2 a 4 turnos).
- Usa SOLO la información que te paso. No inventes datos, nombres, cifras, fechas ni declaraciones. El contexto general que añadas para explicar, que sea muy conocido y prudente.
- Las noticias que estén en gallego, cuéntalas en castellano.
- Real Madrid: NUNCA digas resultados, marcadores, goles ni quién ganó, aunque salgan en alguna noticia: Iago ve los resúmenes después y no quiere spoilers.
- Los cambios de bloque, dentro de la conversación («Vale, y ahora cosas de aquí, de Coruña…»), sin repetir siempre la misma fórmula.

LONGITUD
- Entre {config.PALABRAS_MIN} y {config.PALABRAS_MAX} palabras en total (el programa entero dura de 12 a 15 minutos). Reparto orientativo: apertura 50, portada 850, interes 650, local 550, cierre 60.

SALIDA
- Solo el JSON con la lista «segmentos»: cada turno es un segmento con «bloque», «voz» (A o B) y «texto» (exactamente lo que se dice)."""


def _datos_para_guionista(hoy_dt, noticias):
    def items(lista):
        return [{"titulo": it["titulo"], "fuente": it.get("fuente", ""), "categoria": it.get("categoria", ""),
                 "texto": util.quitar_url(it.get("texto", ""))[:config.TEXTO_MAX_NOTICIA]}
                for it in (lista or [])]
    return {
        "fecha": util.fecha_larga(hoy_dt) + f" de {hoy_dt.year}",
        "presentadores": {k: v["nombre"] for k, v in config.LOCUTORES.items()},
        "portada": items(noticias.get("portada")),
        "interes": items(noticias.get("interes")),
        "local": items(noticias.get("local")),
        "alertas_sanitarias": noticias.get("alertas_sanitarias") or [],
        "madrid": noticias.get("madrid") or {"jugo": False},
    }


class ErrorApi(Exception):
    def __init__(self, codigo, texto):
        super().__init__(f"HTTP {codigo}: {texto[:400]}")
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
    limpios = []
    for s in segs or []:
        bloque = str(s.get("bloque", "")).strip().lower()
        voz = str(s.get("voz", "A")).strip().upper()[:1]
        t = re.sub(r"\s+", " ", str(s.get("texto", ""))).strip()
        # por si se cuela «Lucía:» delante del texto
        t = RE_NOMBRE_DELANTE.sub("", t)
        if bloque not in BLOQUES or not t:
            continue
        limpios.append({"bloque": bloque, "voz": voz if voz in ("A", "B") else "A", "texto": t})
    if len(limpios) < 6:
        raise ValueError("el guion no trae turnos suficientes")
    return limpios


def _espera_429(texto):
    m = re.search(r'"retryDelay"\s*:\s*"(\d+)', texto or "")
    return min(70, int(m.group(1)) + 2) if m else 25


def _pedir_guion(sistema, usuario):
    errores, t0 = [], time.time()
    for modelo in config.MODELOS_TEXTO:
        for intento in range(2):
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
                if e.codigo == 429 and intento == 0:
                    time.sleep(_espera_429(e.texto))
                    continue
                if e.codigo >= 500 and intento == 0:
                    time.sleep(8)
                    continue
                break
            except requests.Timeout:
                errores.append(f"{modelo}: no respondió a tiempo")
                break                          # siguiente modelo
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


def guion_sin_ia(hoy_dt, noticias):
    """Boletín de reserva, sin Gemini: titulares con su primera frase, alternando voces."""
    def primera(t):
        f = re.split(r"(?<=[.!?])\s+", t or "")
        return f[0] if f and len(f[0]) > 30 else (t or "")[:240]

    segs = [{"bloque": "apertura", "voz": "A", "texto": f"Buenos días, Iago. Es {util.fecha_larga(hoy_dt)}."},
            {"bloque": "apertura", "voz": "B", "texto": "Hoy toca un resumen más corto de lo normal. Vamos con lo rápido del día."}]
    voz = "A"
    for bloque, intro in (("portada", "Y ahora, las noticias."), ("interes", "Más cosas de interés."),
                          ("local", "Y en Coruña y Galicia.")):
        lista = noticias.get(bloque) or []
        for k, it in enumerate(lista):
            texto = (intro + " " if k == 0 else "") + f"{it['titulo']}. {primera(it.get('texto', ''))}"
            segs.append({"bloque": bloque, "voz": voz, "texto": texto})
            voz = "B" if voz == "A" else "A"
    segs.append({"bloque": "cierre", "voz": voz, "texto": "Esto ha sido todo por hoy. ¡Que tengas un buen día!"})
    return segs


def escribir(hoy_dt, noticias):
    """Devuelve (segmentos, info) de la parte conversada (apertura, noticias y cierre)."""
    info = {"modelo": None, "avisos": []}
    datos = _datos_para_guionista(hoy_dt, noticias)
    n = sum(len(datos[k]) for k in ("portada", "interes", "local"))
    usuario = "DATOS DE HOY (JSON):\n" + json.dumps(datos, ensure_ascii=False)
    sistema = instrucciones(n)
    segs, modelo, errores = _pedir_guion(sistema, usuario)
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
        segs = guion_sin_ia(hoy_dt, noticias)

    # orden de bloques respetando el orden de los turnos dentro de cada bloque
    segs = sorted(segs, key=lambda s: BLOQUES.index(s["bloque"]))
    if not segs or segs[0]["bloque"] != "apertura":
        segs.insert(0, {"bloque": "apertura", "voz": "A",
                        "texto": f"¡Buenos días, Iago! Es {util.fecha_larga(hoy_dt)}. Vamos con lo rápido del día."})
    for s in segs:
        s["texto"] = _sin_spoilers(s["texto"])
    segs = [s for s in segs if s["texto"]]
    info["palabras"] = sum(util.palabras(s["texto"]) for s in segs)
    return segs, info


def a_markdown(segs, info, hoy_dt, extra=""):
    nombres = {k: v["nombre"] for k, v in config.LOCUTORES.items()}
    titulos = {"apertura": "Apertura", "rapido": "Lo rápido del día", "portada": "Portada",
               "interes": "De interés", "local": "Coruña y Galicia", "cierre": "Cierre"}
    lineas = [f"# Noticiario de Iago · {util.fecha_larga(hoy_dt)}", "",
              f"_Guion: {info.get('modelo')} · {info.get('palabras', 0)} palabras_{extra}", ""]
    actual = None
    for s in segs:
        if s["bloque"] != actual:
            lineas += ["", f"## {titulos.get(s['bloque'], s['bloque'].capitalize())}", ""]
            actual = s["bloque"]
        lineas.append(f"**{nombres.get(s['voz'], s['voz'])}:** {s['texto']}")
        lineas.append("")
    if info.get("avisos"):
        lineas += ["", "---", "", "### Avisos de la generación", ""] + [f"- {a}" for a in info["avisos"]]
    return "\n".join(lineas)
