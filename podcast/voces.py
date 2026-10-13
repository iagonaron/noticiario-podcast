"""Pone voz al guion, como una conversación entre dos personas.

1. Gemini (plan gratuito), en modo conversación: cada tanda de turnos seguidos se genera de una
   vez con las dos voces, así los cambios de turno suenan naturales (como en NotebookLM).
   Hay varios modelos en cadena. Si el límite es por minuto o el servidor está saturado, se
   espera y se repite; si un modelo se queda sin cupo diario o no sirve, las tandas que faltan
   siguen con el siguiente (lo ya hecho se aprovecha). Si una tanda sale rara, se parte en dos.
2. Si ningún modelo de Gemini puede con todo, lo que falte se hace con Edge (voces de Microsoft)
   y, si Edge no responde (desde los servidores de GitHub suele dar 403), con Piper, que funciona
   sin conexión. El pódcast llega siempre.

Todo lo que pasa queda en REGISTRO (solo datos técnicos: modelo, caracteres, segundos; nada del
texto), que acaba en «Diagnóstico.txt» en Dropbox.
"""
import asyncio
import base64
import importlib
import io
import os
import re
import subprocess
import sys
import tempfile
import time
import wave

import requests

from . import config, util

URL_INTERACTIONS = "https://generativelanguage.googleapis.com/v1beta/interactions"
URL_GENERATE = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"

REGISTRO = []


class FalloVoz(Exception):
    pass


class ModeloAgotado(FalloVoz):
    """Cupo diario agotado o modelo que no acepta la petición: hay que pasar al siguiente."""


def anota(texto):
    REGISTRO.append(f"{util.ahora():%H:%M:%S} {texto}")
    util.log(texto)


# ---------------------------------------------------------------- utilidades de audio
def pcm_a_wav(pcm, rate=24000):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return b.getvalue()


def duracion_wav(datos):
    with wave.open(io.BytesIO(datos)) as w:
        return w.getnframes() / float(w.getframerate())


def _frases(texto, maximo):
    if len(texto) <= maximo:
        return [texto]
    frases = re.split(r"(?<=[.!?…])\s+", texto)
    trozos, actual = [], ""
    for f in frases:
        if actual and len(actual) + 1 + len(f) > maximo:
            trozos.append(actual)
            actual = f
        else:
            actual = (actual + " " + f).strip()
    if actual:
        trozos.append(actual)
    return trozos


def tandas(segmentos, maximo=None):
    """Agrupa turnos seguidos en tandas de como mucho `maximo` caracteres (pueden abarcar varios
    bloques: la conversación ya enlaza sola). Menos tandas = menos peticiones al cupo gratuito."""
    maximo = maximo or config.VOZ_MAX_CARACTERES
    salida = []
    for s in segmentos:
        for t in _frases(util.sin_emojis(s["texto"]), maximo):
            turno = {"voz": s["voz"], "texto": t, "bloque": s["bloque"], "noticia": s.get("noticia")}
            ultima = salida[-1] if salida else None
            if ultima and _caracteres(ultima) + len(t) <= maximo:
                ultima["turnos"].append(turno)
            else:
                salida.append({"bloque": s["bloque"], "noticia": s.get("noticia"), "turnos": [turno]})
    return salida


def _caracteres(tanda):
    return sum(len(t["texto"]) for t in tanda["turnos"])


def _partir(tanda):
    """Parte una tanda en dos mitades (por turnos o, si es un solo turno, por frases)."""
    nivel = tanda.get("nivel", 0) + 1
    turnos = tanda["turnos"]
    if len(turnos) > 1:
        total, acum, corte = _caracteres(tanda), 0, 1
        for i, t in enumerate(turnos[:-1], 1):
            acum += len(t["texto"])
            corte = i
            if acum >= total / 2:
                break
        partes = [turnos[:corte], turnos[corte:]]
    else:
        frases = re.split(r"(?<=[.!?…])\s+", turnos[0]["texto"])
        if len(frases) < 2:
            return None
        m = len(frases) // 2
        partes = [[dict(turnos[0], texto=" ".join(frases[:m]))], [dict(turnos[0], texto=" ".join(frases[m:]))]]
    return [{"bloque": p[0]["bloque"], "turnos": p, "nivel": nivel} for p in partes]


def _buscar_audio(obj):
    """Busca en la respuesta el último bloque de audio en base64 (la forma exacta varía según la versión)."""
    hallado = []

    def rec(o):
        if isinstance(o, dict):
            if o.get("type") == "audio" and isinstance(o.get("data"), str):
                hallado.append((o.get("mime_type") or o.get("mimeType") or "", o["data"]))
            if isinstance(o.get("inlineData"), dict) and isinstance(o["inlineData"].get("data"), str):
                hallado.append((o["inlineData"].get("mimeType", ""), o["inlineData"]["data"]))
            if isinstance(o.get("output_audio"), dict) and isinstance(o["output_audio"].get("data"), str):
                hallado.append((o["output_audio"].get("mime_type", ""), o["output_audio"]["data"]))
            for v in o.values():
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)

    rec(obj)
    return hallado[-1] if hallado else (None, None)


def _a_wav(mime, datos_b64):
    datos = base64.b64decode(datos_b64)
    if datos[:4] == b"RIFF":
        return datos
    m = re.search(r"rate=(\d+)", mime or "")
    return pcm_a_wav(datos, int(m.group(1)) if m else 24000)


# ---------------------------------------------------------------- Gemini
def _id(clave):
    """Identificador sin tildes del locutor (Lucia, Martin) para el modo conversación."""
    return util.sin_tildes(config.LOCUTORES[clave]["nombre"]).replace(" ", "")


def _cabeceras():
    return {"x-goog-api-key": os.environ.get("GEMINI_API_KEY", ""), "Content-Type": "application/json"}


def _post(url, cuerpo, etiqueta):
    try:
        r = requests.post(url, json=cuerpo, headers=_cabeceras(), timeout=config.VOZ_TIMEOUT)
    except requests.RequestException as e:
        raise FalloVoz(f"{etiqueta}: {type(e).__name__}")
    if r.status_code != 200:
        # el texto completo sirve para distinguir el cupo diario («PerDay») del de por minuto
        raise FalloVoz(f"{etiqueta} HTTP {r.status_code}: {r.text[:4000]}")
    try:
        datos = r.json()
    except ValueError:
        raise FalloVoz(f"{etiqueta}: la respuesta no es JSON")
    mime, audio = _buscar_audio(datos)
    if not audio:
        motivo = re.findall(r'"(?:finishReason|finish_reason|status)"\s*:\s*"([^"]+)"', r.text)
        raise FalloVoz(f"{etiqueta}: respuesta sin audio {motivo[:3]}")
    return _a_wav(mime, audio)


def _gemini_interactions(modelo, tanda):
    voces = sorted({t["voz"] for t in tanda["turnos"]})
    contenido = []
    for t in tanda["turnos"]:
        meta = {"type": "speech_metadata", "style": config.ESTILO_VOZ}
        if len(voces) > 1:
            meta["speaker"] = _id(t["voz"])
        contenido.append({"type": "text", "text": t["texto"], "annotations": [meta]})
    if len(voces) > 1:
        speech = {"mode": "conversational",
                  "speakers": [{"speaker": _id(v), "voice": config.LOCUTORES[v]["gemini"]} for v in voces]}
    else:
        speech = [{"voice": config.LOCUTORES[voces[0]]["gemini"]}]
    cuerpo = {"model": modelo, "input": [{"type": "user_input", "content": contenido}],
              "response_format": {"type": "audio"}, "generation_config": {"speech_config": speech}}
    return _post(URL_INTERACTIONS, cuerpo, f"{modelo} (interactions)")


def _gemini_generate(modelo, tanda):
    voces = sorted({t["voz"] for t in tanda["turnos"]})
    if len(voces) > 1:
        texto = (f"Estilo: {config.ESTILO_VOZ}. Lee esta conversación entre {_id('A')} y {_id('B')}, tal cual:\n\n"
                 + "\n".join(f"{_id(t['voz'])}: {t['texto']}" for t in tanda["turnos"]))
        speech = {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
            {"speaker": _id(v), "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": config.LOCUTORES[v]["gemini"]}}}
            for v in voces]}}
    else:
        texto = (f"Estilo: {config.ESTILO_VOZ}. Lee en voz alta, tal cual, haciendo una pausa entre párrafos:\n\n"
                 + "\n\n".join(t["texto"] for t in tanda["turnos"]))
        speech = {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": config.LOCUTORES[voces[0]]["gemini"]}}}
    cuerpo = {"contents": [{"parts": [{"text": texto}]}],
              "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": speech}}
    return _post(URL_GENERATE.format(modelo=modelo), cuerpo, f"{modelo} (generate)")


def _llamada(via, modelo, tanda):
    if via == "piper":                       # solo para pruebas sin gastar cupo («piper:local»)
        return _piper_tanda(tanda)
    return (_gemini_interactions if via == "interactions" else _gemini_generate)(modelo, tanda)


def _piper_tanda(tanda):
    """Una tanda de una sola voz con Piper, con pausas entre turnos como las de una lectura seguida."""
    import random
    from pydub import AudioSegment
    from piper import SynthesisConfig
    voces = _piper_cargar()
    voz, sid = voces[tanda["turnos"][0]["voz"]]
    total = AudioSegment.silent(duration=300, frame_rate=24000)
    for t in tanda["turnos"]:
        b = io.BytesIO()
        with wave.open(b, "wb") as w:
            voz.synthesize_wav(t["texto"], w, syn_config=SynthesisConfig(speaker_id=sid, length_scale=config.PIPER_LENTITUD))
        seg = AudioSegment.from_wav(io.BytesIO(b.getvalue())).set_channels(1).set_frame_rate(24000).set_sample_width(2)
        total += seg + AudioSegment.silent(duration=random.randint(300, 750), frame_rate=24000)
    out = io.BytesIO()
    total.export(out, format="wav")
    return out.getvalue()


def _razonable(wav, tanda):
    """¿Dura lo que debería? (detecta audios cortados o con divagaciones)."""
    seg = duracion_wav(wav)
    palabras = sum(util.palabras(t["texto"]) for t in tanda["turnos"])
    esperado = max(1.5, palabras / 2.8)      # ~170 palabras por minuto en conversación
    return 0.55 * esperado <= seg <= 1.8 * esperado + 3, seg, esperado


def _resumen(msg):
    """Error en una línea: «modelo HTTP 429: mensaje» (sin el JSON entero)."""
    m = re.search(r'"message"\s*:\s*"([^"]{0,200})', msg or "")
    cabeza = (msg or "").split(":", 1)[0] if " HTTP " in (msg or "") else ""
    codigo = re.search(r"HTTP (\d{3})", msg or "")
    if m:
        return f"{cabeza.split(' HTTP')[0]} HTTP {codigo.group(1) if codigo else '?'}: {m.group(1)}"
    return re.sub(r"\s+", " ", msg or "")[:260]


def _es_cuota(msg):
    m = (msg or "").lower()
    return "http 429" in m or "resource_exhausted" in m or "rate limit" in m or "too_many_requests" in m


def _segundos_espera(msg):
    m = (msg or "").lower()
    r = re.search(r'"retrydelay"\s*:\s*"(\d+)', m)
    if r:
        return int(r.group(1))
    r = re.search(r"retry in\s*(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+(?:\.\d+)?)s)?", m)
    if r and any(r.groups()):
        h, mi, s = r.groups()
        return int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)
    return 30


def _clasifica(msg):
    """'cambiar' (cupo diario agotado o el modelo no acepta la petición), 'esperar' (límite por
    minuto o servidor saturado) u 'otro' (audio raro, tiempo agotado… → partir la tanda)."""
    m = (msg or "").lower()
    if re.search(r"http (400|401|403|404)\b", m) or "timeout" in m:
        return "cambiar"          # petición que el modelo no acepta, o que no contesta a tiempo
    if _es_cuota(m):
        if "per day" in m or "per_day" in m or "perday" in m or "daily" in m or "requests per day" in m:
            return "cambiar"
        return "cambiar" if _segundos_espera(m) > 150 else "esperar"
    if re.search(r"http (500|502|503|504)\b", m) or "overloaded" in m or "unavailable" in m or "connectionerror" in m:
        return "esperar"
    return "otro"


def _pedir(via, modelo, tanda):
    """Una tanda con un modelo: reintenta si toca esperar; ModeloAgotado si hay que cambiar de
    modelo; FalloVoz si conviene partir la tanda."""
    n_car, n_t = _caracteres(tanda), len(tanda["turnos"])
    error = "sin intentos"
    for intento in range(4):
        t0 = time.time()
        try:
            wav = _llamada(via, modelo, tanda)
        except FalloVoz as e:
            error = str(e)
            tipo = _clasifica(error)
            anota(f"  ✗ {modelo}: {n_car} car./{n_t} turnos · {time.time() - t0:.0f}s · {tipo} · {_resumen(error)}")
            if tipo == "cambiar":
                raise ModeloAgotado(_resumen(error))
            if tipo == "esperar":
                if intento < 3:
                    time.sleep(min(90, max(8, _segundos_espera(error) + 3)))
                    continue
                raise ModeloAgotado(_resumen(error))     # sigue saturado o sin cupo: otro modelo
            raise FalloVoz(_resumen(error))
        ok, seg, esp = _razonable(wav, tanda)
        anota(f"  {'✓' if ok else '✗'} {modelo}: {n_car} car./{n_t} turnos → {seg:.0f}s de audio "
              f"(esperado ~{esp:.0f}s) en {time.time() - t0:.0f}s")
        if ok:
            return wav
        raise FalloVoz(f"duración rara ({seg:.0f}s, esperaba ~{esp:.0f}s)")
    raise FalloVoz(error)


def sintetizar_gemini(lista):
    """Recorre las tandas en orden. Devuelve (hechas, pendientes, modelos usados, errores):
    `hechas` es el principio del episodio con su audio y `pendientes`, lo que falte."""
    hechas, usados, errores = [], [], []
    pendientes = list(lista)
    if not os.environ.get("GEMINI_API_KEY"):
        return hechas, pendientes, usados, ["Falta el secreto GEMINI_API_KEY"]
    for via, modelo in config.MODELOS_VOZ:
        if not pendientes:
            break
        anota(f"Voz con {modelo} ({via}) · faltan {len(pendientes)} tandas")
        partidas = 0
        while pendientes:
            tanda = pendientes[0]
            try:
                wav = _pedir(via, modelo, tanda)
            except ModeloAgotado as e:
                errores.append(f"{modelo}: {str(e)[:200]}")
                break
            except FalloVoz as e:
                partes = _partir(tanda) if tanda.get("nivel", 0) < 2 and partidas < 4 else None
                if partes:
                    partidas += 1
                    anota(f"  → parto la tanda en dos ({len(partes[0]['turnos'])}+{len(partes[1]['turnos'])} turnos)")
                    pendientes[0:1] = partes
                    continue
                errores.append(f"{modelo}: {str(e)[:200]}")
                break
            hechas.append((tanda, wav))
            pendientes.pop(0)
            if modelo not in usados:
                usados.append(modelo)
    return hechas, pendientes, usados, errores


# ---------------------------------------------------------------- Edge (reserva 1)
async def _edge_uno(texto, voz, ruta):
    import edge_tts
    await edge_tts.Communicate(texto, voz, rate=config.EDGE_VELOCIDAD).save(ruta)


def _juntar(trozos):
    """Une los audios de los turnos de una tanda con una pausa corta y devuelve un WAV."""
    from pydub import AudioSegment
    total = None
    for seg in trozos:
        seg = seg.set_channels(1).set_frame_rate(24000).set_sample_width(2)
        total = seg if total is None else total + AudioSegment.silent(duration=250, frame_rate=24000) + seg
    b = io.BytesIO()
    total.export(b, format="wav")
    return b.getvalue()


def sintetizar_edge(lista, carpeta):
    """Turno a turno con Edge. Si el primer turno ya falla, no insiste (desde GitHub suele estar bloqueado)."""
    from pydub import AudioSegment
    audios, primero = [], True
    for n, tanda in enumerate(lista, 1):
        trozos = []
        for k, t in enumerate(tanda["turnos"], 1):
            ruta = os.path.join(carpeta, f"edge_{n:02d}_{k:02d}.mp3")
            for intento in range(1 if primero else 3):
                try:
                    asyncio.run(_edge_uno(t["texto"], config.LOCUTORES[t["voz"]]["edge"], ruta))
                    trozos.append(AudioSegment.from_file(ruta))
                    break
                except Exception as e:
                    if primero or intento == 2:
                        raise FalloVoz(f"Edge falló en la tanda {n}: {str(e)[:160]}")
                    time.sleep(4 * (intento + 1))
            primero = False
        audios.append(_juntar(trozos))
    return audios


# ---------------------------------------------------------------- Piper (reserva 2, sin conexión)
def _piper_cargar():
    try:
        import piper  # noqa: F401
    except ImportError:
        anota("Instalo Piper (voz sin conexión)…")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "piper-tts"], check=True, timeout=900)
        importlib.invalidate_caches()
    from pathlib import Path
    from piper import PiperVoice
    from piper.download_voices import download_voice
    carpeta = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()) / "voces-piper"
    carpeta.mkdir(parents=True, exist_ok=True)
    modelos, voces = {}, {}
    for clave, loc in config.LOCUTORES.items():
        modelo, _, hablante = loc["piper"].partition(":")
        if modelo not in modelos:
            if not (carpeta / f"{modelo}.onnx").exists():
                download_voice(modelo, carpeta)
            modelos[modelo] = PiperVoice.load(str(carpeta / f"{modelo}.onnx"))
        v = modelos[modelo]
        mapa = dict(getattr(v.config, "speaker_id_map", {}) or {})
        sid = mapa.get(hablante) if hablante in mapa else (min(mapa.values()) if mapa else None)
        voces[clave] = (v, sid)
    return voces


def sintetizar_piper(lista):
    voces = _piper_cargar()          # primero: instala Piper si hace falta
    from piper import SynthesisConfig
    from pydub import AudioSegment
    audios = []
    for tanda in lista:
        trozos = []
        for t in tanda["turnos"]:
            voz, sid = voces[t["voz"]]
            b = io.BytesIO()
            with wave.open(b, "wb") as w:
                voz.synthesize_wav(t["texto"], w, syn_config=SynthesisConfig(speaker_id=sid, length_scale=config.PIPER_LENTITUD))
            trozos.append(AudioSegment.from_wav(io.BytesIO(b.getvalue())))
        audios.append(_juntar(trozos))
    return audios


def _respaldo(pendientes, carpeta):
    """Lo que Gemini no pudo hacer: Edge y, si no, Piper."""
    if config.MOTOR_VOZ != "piper":
        try:
            t0 = time.time()
            audios = sintetizar_edge(pendientes, carpeta)
            anota(f"Edge: {len(pendientes)} tandas en {time.time() - t0:.0f}s")
            return audios, "Edge"
        except Exception as e:
            anota(f"Edge no disponible: {str(e)[:200]}")
    t0 = time.time()
    audios = sintetizar_piper(pendientes)
    anota(f"Piper: {len(pendientes)} tandas en {time.time() - t0:.0f}s")
    return audios, "Piper"


# ---------------------------------------------------------------- todo junto
def sintetizar_tandas(segmentos, carpeta):
    """Método anterior (reserva): tandas con las dos voces a la vez. Devuelve (unidades, motor, avisos)."""
    lista = tandas(segmentos)
    anota(f"{len(lista)} tandas · {sum(_caracteres(t) for t in lista)} caracteres")
    avisos, pares, partes_motor = [], [], []
    pendientes = list(lista)
    if config.MOTOR_VOZ not in ("edge", "piper"):
        hechas, pendientes, usados, errores = sintetizar_gemini(lista)
        pares += hechas
        if usados:
            partes_motor.append("Gemini · " + " + ".join(usados))
        if errores:
            avisos.append("Voz: algún modelo de Gemini se quedó sin cupo o falló: " + " | ".join(errores)[:700])
    if pendientes:
        if pares:
            avisos.append(f"Voz: Gemini hizo {len(pares)} tandas; las {len(pendientes)} últimas van con voz de reserva.")
        else:
            avisos.append("Voz: Gemini no pudo; el episodio va entero con voz de reserva.")
        audios, nombre = _respaldo(pendientes, carpeta)
        pares += list(zip(pendientes, audios))
        partes_motor.append(nombre)
    unidades = [{"bloque": t["bloque"], "noticia": t.get("noticia"), "wav": a, "segundos": duracion_wav(a),
                 "palabras": sum(util.palabras(x["texto"]) for x in t["turnos"]),
                 "voces": "".join(sorted({x["voz"] for x in t["turnos"]}))}
                for t, a in pares]
    return unidades, " + ".join(partes_motor), avisos


# ---------------------------------------------------------------- por voces (método principal)
# Cada voz se genera aparte y SIEMPRE con el mismo modelo de principio a fin (así no cambia de
# timbre ni se mezclan): primero todas las frases de Lucía, luego las de Martín, en lotes de
# turnos enteros. Después se cortan turno a turno (alinear.py) y el montaje intercala el diálogo.
AGOTADOS = set()


def nombre(clave):
    return config.LOCUTORES[clave]["nombre"]


def _lotes_de(turnos, maximo):
    lotes, actual, n = [], [], 0
    for idx, t in turnos:
        if actual and n + len(t) > maximo:
            lotes.append(actual)
            actual, n = [], 0
        actual.append((idx, t))
        n += len(t)
    if actual:
        lotes.append(actual)
    return lotes


def _voz_con_modelo(via, modelo, clave, lotes):
    """Todas las frases de una voz con un mismo modelo. Devuelve {índice: wav}."""
    from . import alinear
    piezas, pendientes = {}, list(lotes)
    presupuesto = len(lotes) * 3
    while pendientes:
        lote = pendientes.pop(0)
        if presupuesto <= 0:
            raise ModeloAgotado("demasiados reintentos para esta voz")
        presupuesto -= 1
        tanda = {"bloque": "voz", "turnos": [{"voz": clave, "texto": t, "bloque": "voz"} for _, t in lote]}
        try:
            wav = _pedir(via, modelo, tanda)
            if len(lote) == 1:
                piezas[lote[0][0]] = wav
                continue
            tramos, resumen = alinear.cortes(wav, [t for _, t in lote])
            anota(f"    ✂ {resumen}")
            for (idx, _), (a, b) in zip(lote, tramos):
                piezas[idx] = alinear.recortar(wav, a, b)
        except ModeloAgotado:
            raise
        except (FalloVoz, alinear.ErrorAlineado) as e:
            if len(lote) == 1:
                raise FalloVoz(f"un turno no sale: {str(e)[:160]}")
            m = len(lote) // 2
            anota(f"    → {str(e)[:120]} · parto el lote en {m}+{len(lote) - m} turnos")
            pendientes[0:0] = [lote[:m], lote[m:]]
    return piezas


def _reserva_turnos(clave, turnos, carpeta):
    """Una voz entera con Edge o, si no deja, con Piper (sin conexión), turno a turno."""
    lista = [{"bloque": "voz", "turnos": [{"voz": clave, "texto": t, "bloque": "voz"}]} for _, t in turnos]
    if config.MOTOR_VOZ != "piper":
        try:
            audios = sintetizar_edge(lista, carpeta)
            return {idx: a for (idx, _), a in zip(turnos, audios)}, "Edge"
        except Exception as e:
            anota(f"Edge no disponible: {str(e)[:160]}")
    audios = sintetizar_piper(lista)
    return {idx: a for (idx, _), a in zip(turnos, audios)}, "Piper"


def sintetizar_por_voces(segmentos, carpeta):
    """Devuelve ({índice de segmento: wav}, {voz: motor}, avisos)."""
    por_voz = {}
    for i, s in enumerate(segmentos):
        por_voz.setdefault(s["voz"], []).append((i, util.sin_emojis(s["texto"])))
    wavs, motores, avisos = {}, {}, []
    for clave in sorted(por_voz):
        turnos = por_voz[clave]
        lotes = _lotes_de(turnos, config.VOZ_MAX_CARACTERES)
        hecho = False
        if config.MOTOR_VOZ not in ("edge", "piper") and os.environ.get("GEMINI_API_KEY"):
            for via, modelo in config.MODELOS_VOZ:
                if modelo in AGOTADOS:
                    continue
                anota(f"Voz de {nombre(clave)} con {modelo} ({via}) · {len(turnos)} turnos en {len(lotes)} lotes")
                try:
                    wavs.update(_voz_con_modelo(via, modelo, clave, lotes))
                    motores[clave] = modelo
                    hecho = True
                    break
                except FalloVoz as e:
                    if _es_cuota(str(e)) or "per day" in str(e).lower():
                        AGOTADOS.add(modelo)
                    avisos.append(f"Voz de {nombre(clave)}: {modelo} no pudo ({str(e)[:160]}); se rehace entera con otro")
                    anota(avisos[-1])
        if not hecho:
            piezas, motor = _reserva_turnos(clave, turnos, carpeta)
            wavs.update(piezas)
            motores[clave] = motor
            avisos.append(f"Voz de {nombre(clave)}: con voz de reserva ({motor})")
    return wavs, motores, avisos


def sintetizar(segmentos, carpeta):
    """Devuelve (piezas, motor, avisos). Cada pieza: {'wav', 'bloque', 'noticia', 'voz', 'palabras', 'segundos'}."""
    anota(f"{len(segmentos)} turnos · {sum(len(s['texto']) for s in segmentos)} caracteres")
    try:
        wavs, motores, avisos = sintetizar_por_voces(segmentos, carpeta)
        piezas = []
        for i, s in enumerate(segmentos):
            w = wavs[i]
            piezas.append({"wav": w, "bloque": s["bloque"], "noticia": s.get("noticia"), "voz": s["voz"],
                           "palabras": util.palabras(s["texto"]), "segundos": duracion_wav(w)})
        motor = " · ".join(f"{nombre(k)}: {v}" for k, v in sorted(motores.items()))
        return piezas, motor, avisos
    except Exception as e:
        anota(f"El método por voces falló ({type(e).__name__}: {str(e)[:200]}); uso el de tandas conversadas")
        unidades, motor, avisos = sintetizar_tandas(segmentos, carpeta)
        piezas = [{"wav": u["wav"], "bloque": u["bloque"], "noticia": u.get("noticia"), "voz": u["voces"],
                   "palabras": u["palabras"], "segundos": u["segundos"]} for u in unidades]
        return piezas, motor + " (tandas)", avisos + [f"Voz: el método por voces falló: {str(e)[:200]}"]
