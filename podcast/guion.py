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


def _bloques(datos):
    """Bloques que hay hoy (si un bloque viene vacío, no se le reservan palabras)."""
    hay = [b for b in ("titulares", "local", "interes") if datos.get(b)]
    if datos.get("distinto_basico"):
        hay.append("distinto")
    return hay


def _locales_a_contar(datos):
    """En local se cuentan 3 (o 4 si de Galicia hay algo que cuentan muchos medios)."""
    hay = len(datos.get("local") or [])
    gordo = any((it.get("medios") or 0) >= config.MEDIOS_NOTICIA_GORDA for it in (datos.get("local") or [])
                if isinstance(it, dict))
    return min(hay, config.LOCAL_MAX + (1 if gordo else 0))


def _palabras_bloque(datos, b):
    if b == "distinto":
        return config.REPARTO["distinto"]
    n = _locales_a_contar(datos) if b == "local" else len(datos.get(b) or [])
    return n * config.PALABRAS_POR_NOTICIA[b]


def _objetivo(datos):
    """(mínimo, máximo) de palabras de lo que escribe la IA, según las noticias que hay hoy."""
    total = sum(_palabras_bloque(datos, b) for b in _bloques(datos)) or 600
    return int(total * 0.9), int(total * 1.08)


def instrucciones(n_noticias, con_plan, datos=None):
    datos = datos or {"titulares": [1] * 7, "local": [1] * 3, "interes": [1] * 3, "distinto_basico": con_plan}
    minimo, maximo = _objetivo(datos)
    local_n = _locales_a_contar(datos)
    local_n = f"{local_n} (tres de siempre y una más por lo gordo de Galicia)" if local_n > config.LOCAL_MAX else str(local_n)
    reparto = ", ".join(f"{b} {_palabras_bloque(datos, b)}" + (f" (unas {config.PALABRAS_POR_NOTICIA[b]} por noticia)"
                                                               if b in config.PALABRAS_POR_NOTICIA else "")
                        for b in _bloques(datos))
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
- Diálogo SIEMPRE: cada noticia la cuentan entre los dos, alternando la voz en cada turno (A, B, A, B…). Nunca dos turnos seguidos de la misma voz y ninguna noticia contada por una voz sola.
- Ágil y al grano: cada noticia en 4 o 5 turnos (las dos más importantes del día, hasta 6), de 20 a 40 palabras cada uno. Lo esencial, sin rodeos ni repeticiones.
- Uno cuenta y el otro pregunta lo que se preguntaría cualquiera («¿y eso en qué me afecta?», «a ver, explícame eso»), reacciona («¡no me digas!», «ojo con esto»), resume o pone un ejemplo. Se van turnando ese papel.
- Una pregunta la responde SIEMPRE la otra voz, en el turno siguiente: nunca preguntes y te respondas en el mismo turno.
- Español de España, coloquial y natural. Desenfadado, con humor ligero cuando cuadre, sin pasarse: nada de chistes malos, risas escritas, gritos ni exageraciones.
- Que se entienda TODO a la primera: palabras sencillas, comparaciones con la vida diaria, cifras redondeadas («casi el doble», «unos ciento sesenta mil»), siglas explicadas, nada de jerga.
- Escribe las cifras con letras, tal como se dicen («dos mil veintiséis», «el veinticinco por ciento»).
- Escribe solo lo que se dice: sin acotaciones, sin nombres delante, sin paréntesis, sin enlaces, sin listas, sin emojis.
- No des por hecho los gustos, costumbres o planes de Iago ni le digas qué le va a interesar{" (salvo en el momento Distinto Básico, que es para eso)" if con_plan else ""}. Fuera de ese momento, nada de perros, paseos ni desayunos.

BLOQUES, EN ESTE ORDEN (antes, el programa ya dice la fecha, los cumpleaños, la agenda y el tiempo: no hables de eso)
1. titulares: las noticias de «titulares» (la portada de El País Exprés). Empieza directamente con la primera, sin preámbulos.
2. local: de A Coruña y de toda Galicia, con un enlace muy corto al empezar («Y aquí, en Galicia…», «Y en Coruña…»). En «local» te paso más de las que caben: ELIGE {local_n} por importancia para alguien que vive en A Coruña (lo que pasa en toda Galicia cuenta tanto como lo de Coruña). Si en Galicia ha pasado algo gordo —un terremoto que se ha notado, un temporal, un incendio grave, un accidente con víctimas, una sequía, una huelga general…— va SIEMPRE y la primera. «medios» dice cuántos medios la están contando: cuantos más, más importante. Las que no elijas, ni las menciones.
3. interes: las de «interes» (ciencia, salud, economía, tecnología…). Si hay alertas sanitarias, se dicen claras al final de este bloque; si no hay, ni se mencionan.{chr(10) + "4. distinto: el momento Distinto Básico." if con_plan else ""}
Entre una noticia y la siguiente sonará una ráfaga de música, así que no hacen falta frases de enlace del tipo «cambiando de tema».

QUÉ CONTAR
- Cuenta TODAS las de «titulares» e «interes» y las {local_n} locales que elijas ({n_noticias} en total), salvo las repetidas y las que sean solo del tiempo.
- Para cada noticia: qué ha pasado, explicado fácil; por qué importa o en qué le afecta a una persona normal; y, si lo hay, un detalle curioso o qué va a pasar ahora.
- Las dos más importantes del día, con algo más de calma; el resto, en cuatro turnos.
- Usa SOLO la información que te paso. No inventes datos, nombres, cifras, fechas ni declaraciones.
- Si de una noticia hay poca información, cuéntala en menos turnos: nunca rellenes con opiniones, moralejas ni frases genéricas («habrá que seguirlo de cerca», «da que pensar»).
- Las noticias en gallego, cuéntalas en castellano.
- Deportes: NUNCA digas resultados, marcadores, goles ni quién ganó.
{plan}
NUMERACIÓN
- Cada turno lleva «noticia»: el número de la noticia que se está contando, empezando por 1 y siguiendo en orden por todo el programa (los titulares 1, 2, 3…, y local e interes siguen la cuenta). Todos los turnos de una misma noticia llevan el mismo número.{" El momento Distinto Básico es la última." if con_plan else ""}

LONGITUD
- Entre {minimo} y {maximo} palabras en total: las noticias tienen que caber en unos 12 minutos. Reparto: {reparto}. Ajústate a esa longitud: ni mucho más corto ni más largo.

SALIDA
- Solo el JSON con «segmentos»: cada turno con «bloque», «noticia», «voz» (A o B) y «texto» (exactamente lo que se dice)."""


def candidatas_locales(noticias):
    """Las locales del noticiario (sobre todo de Coruña) más lo que más medios cuentan de toda Galicia,
    sin repetir. Cada una con «medios» si se sabe cuántos medios la cuentan. El guionista elige."""
    from .noticias import misma_noticia
    locales = [{"titulo": it["titulo"], "fuente": it.get("fuente", ""), "categoria": it.get("categoria", ""),
                "texto": util.quitar_url(it.get("texto", ""))[:config.TEXTO_MAX_NOTICIA]}
               for it in (noticias.get("local") or [])[:config.LOCAL_CANDIDATAS]]
    for g in noticias.get("galicia") or []:
        igual = next((l for l in locales if misma_noticia(l["titulo"], g["titulo"])), None)
        if igual:
            igual["medios"] = g["medios"]
        else:
            locales.append({"titulo": g["titulo"], "fuente": g["fuente"], "categoria": "Galicia",
                            "texto": g["texto"][:config.TEXTO_MAX_NOTICIA], "medios": g["medios"]})
    return locales


def _datos_para_guionista(hoy_dt, noticias, plan=None):
    def items(lista):
        return [{"titulo": it["titulo"], "fuente": it.get("fuente", ""), "categoria": it.get("categoria", ""),
                 "texto": util.quitar_url(it.get("texto", ""))[:config.TEXTO_MAX_NOTICIA]}
                for it in (lista or [])]
    datos = {
        "fecha": util.fecha_larga(hoy_dt) + f" de {hoy_dt.year}",
        "titulares": items(noticias.get("portada")),
        "local": candidatas_locales(noticias),
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


_SIN_PENSAR_CORTO = set()      # modelos que no admiten «thinkingLevel»


def _llamar(modelo, sistema, usuario, con_esquema=True, esquema=None):
    clave = os.environ.get("GEMINI_API_KEY", "")
    cfg = {"temperature": 0.85, "responseMimeType": "application/json", "maxOutputTokens": 32000}
    if con_esquema:
        cfg["responseSchema"] = esquema or ESQUEMA
    if config.GUION_PENSAR and modelo not in _SIN_PENSAR_CORTO:
        cfg["thinkingConfig"] = {"thinkingLevel": config.GUION_PENSAR}
    cuerpo = {
        "systemInstruction": {"parts": [{"text": sistema}]},
        "contents": [{"role": "user", "parts": [{"text": usuario}]}],
        "generationConfig": cfg,
    }
    r = requests.post(URL.format(modelo=modelo), json=cuerpo, timeout=420,
                      headers={"x-goog-api-key": clave, "Content-Type": "application/json"})
    if r.status_code == 400 and "thinking" in r.text.lower() and "thinkingConfig" in cfg:
        _SIN_PENSAR_CORTO.add(modelo)
        return _llamar(modelo, sistema, usuario, con_esquema, esquema)
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


RE_RESPUESTA = re.compile(r"(?<=\?)\s+(?=(?:Pues|Sí|Si,|No,|Claro|Exacto|Muchísimo|Totalmente|Eso es|Así es|"
                          r"Efectivamente|Tal cual|Desde luego|Para nada|Qué va|Justo)\b)")


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
            gordas = [g for g in noticias.get("galicia") or [] if g.get("medios", 0) >= config.MEDIOS_NOTICIA_GORDA]
            lista = (gordas[:1] + lista)[:config.LOCAL_MAX + (1 if gordas else 0)]
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
    n = len(datos["titulares"]) + len(datos["interes"]) + _locales_a_contar(datos)
    usuario = "DATOS DE HOY (JSON):\n" + json.dumps(datos, ensure_ascii=False)
    sistema = instrucciones(n, bool(plan), datos)
    segs, modelo, errores = _pedir_guion(sistema, usuario)
    info["avisos"] += errores
    if segs:
        total = sum(util.palabras(s["texto"]) for s in segs)
        minimo, maximo = _objetivo(datos)
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
    autorespuestas = sum(1 for s in segs if len(RE_RESPUESTA.split(s["texto"], maxsplit=1)) == 2)
    info["dialogo"] = (f"{len(segs)} turnos · {unidos} turnos seguidos de la misma voz unidos · "
                       f"{largos} turnos de más de 60 palabras · {autorespuestas} turnos que preguntan y se responden")
    info["palabras"] = sum(util.palabras(s["texto"]) for s in segs)
    return segs, info


def _distinto_plantilla(plan, primera, numero):
    """Por si la IA no responde: el plan contado con frases fijas, alternando voces."""
    otra = "B" if primera == "A" else "A"
    frases = [(primera, f"Y para terminar, el momento Distinto Básico: {plan.get('titulo')}."),
              (otra, str(plan.get("que_es") or "")),
              (primera, " ".join(x for x in (f"Es {plan['cuando']}" if plan.get("cuando") else "",
                                              f"en {plan['lugar']}." if plan.get("lugar") else "") if x)),
              (otra, " ".join(x for x in (f"Precio: {plan['precio']}." if plan.get("precio") else "",
                                           f"Reserva: {plan['reserva']}." if plan.get("reserva") else "") if x))]
    comer = plan.get("comer") if isinstance(plan.get("comer"), dict) else None
    if comer and comer.get("nombre"):
        frases.append((primera, f"Y para comer cerca, {comer['nombre']}" + (f": {comer['que']}." if comer.get("que") else ".")))
    return [{"bloque": "distinto", "noticia": numero, "voz": v, "texto": t} for v, t in frases if t.strip()]


def escribir_distinto(plan, primera, numero):
    """El momento Distinto Básico en diálogo (llamada corta aparte). Devuelve (segmentos, modelo, avisos)."""
    sistema = f"""Escribes el último bloque de un pódcast diario de noticias que escucha Iago en A Coruña: el «momento Distinto Básico», la propuesta de plan de hoy para él y su pareja, Laura.
- Diálogo entre dos voces que se alternan, empezando por la voz {primera}: entre 4 y 6 turnos, unas {config.REPARTO['distinto']} palabras en total, cada turno de 45 palabras como mucho.
- El primer turno empieza exactamente con: «Y para terminar, el momento Distinto Básico.»
- Cuenta: qué es (explicado a quien no lo conoce), cuándo y dónde, cuánto cuesta, si hay que reservar y con cuánta antelación, y dónde comer vegano cerca. Di por qué les puede gustar. Si en «visma» pone true, se puede decir que Visma, su perra, también puede ir.
- Usa SOLO los datos que te paso: ni fechas, ni horas, ni precios, ni sitios inventados. Si un dato no viene, no lo digas. Las direcciones web no se leen.
- Español de España, coloquial y natural, hablándole a Iago de tú (nunca «a Iago le…» en tercera persona); sin saludos, sin nombres de los presentadores, sin despedida. Cifras con letras.
- Una pregunta la responde siempre la otra voz; nada de rellenos.
- Salida: solo el JSON con «segmentos» (bloque «distinto», noticia {numero}, voz A o B, texto)."""
    if plan.get("recordatorio"):
        sistema += ("\n- Hoy NO hay plan nuevo: es un RECORDATORIO de una propuesta de otro día que sigue en pie. "
                    "Dilo con naturalidad justo después de la primera frase (por ejemplo: «hoy no hemos encontrado "
                    "nada nuevo, pero ojo, que sigue en pie…») y céntrate en cuándo es y si hay que reservar. "
                    "El «cuando» ya viene dicho respecto a hoy: úsalo tal cual.")
    datos = {k: v for k, v in plan.items() if k not in ("fuentes", "fuente", "modelo", "lectura", "recordatorio",
                                                         "recordado", "propuesto")}
    usuario = "PROPUESTA (JSON):\n" + json.dumps(datos, ensure_ascii=False)
    avisos = []
    for modelo in config.MODELOS_TEXTO[:3]:
        try:
            texto = _llamar(modelo, sistema, usuario)
            segs = [s for s in _parsear_todo(texto) if s["texto"]]
            if len(segs) >= 2:
                for s in segs:
                    s["bloque"], s["noticia"] = "distinto", numero
                segs, _ = _unir_seguidos(segs)
                return segs, modelo, avisos
        except Exception as e:
            avisos.append(f"Distinto Básico (guion) · {modelo}: {str(e)[:160]}")
    return _distinto_plantilla(plan, primera, numero), "plantilla", avisos


def _parsear_todo(texto):
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip())
    j = json.loads(texto)
    out = []
    for s in (j.get("segmentos") if isinstance(j, dict) else j) or []:
        voz = str(s.get("voz", "A")).strip().upper()[:1]
        t = RE_NOMBRE_DELANTE.sub("", re.sub(r"\s+", " ", str(s.get("texto", ""))).strip())
        out.append({"bloque": "distinto", "noticia": 0, "voz": voz if voz in ("A", "B") else "A", "texto": t})
    return out


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
