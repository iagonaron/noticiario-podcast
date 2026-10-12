"""Pone voz al guion, como una conversación entre dos personas.

1. Gemini (plan gratuito), en modo conversación: cada tanda de turnos seguidos se genera de una
   vez con las dos voces, así los cambios de turno suenan naturales (como en NotebookLM).
   Se elige el primer modelo de voz que responda y se usa el mismo para todo el episodio.
2. Si Gemini falla en cualquier tanda, el episodio ENTERO se hace con Edge (voces de Microsoft),
   turno a turno, para que suene coherente. El pódcast llega igual.
"""
import asyncio
import base64
import io
import os
import re
import time
import wave

import requests

from . import config, util

URL_INTERACTIONS = "https://generativelanguage.googleapis.com/v1beta/interactions"
URL_GENERATE = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"


class FalloVoz(Exception):
    pass


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


def tandas(segmentos, maximo=config.VOZ_MAX_CARACTERES):
    """Agrupa turnos seguidos del mismo bloque en tandas de como mucho `maximo` caracteres."""
    salida = []
    for s in segmentos:
        for t in _frases(s["texto"], maximo):
            turno = {"voz": s["voz"], "texto": t}
            ultima = salida[-1] if salida else None
            if (ultima and ultima["bloque"] == s["bloque"]
                    and sum(len(x["texto"]) for x in ultima["turnos"]) + len(t) <= maximo):
                ultima["turnos"].append(turno)
            else:
                salida.append({"bloque": s["bloque"], "turnos": [turno]})
    return salida


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
    r = requests.post(URL_INTERACTIONS, json=cuerpo, headers=_cabeceras(), timeout=300)
    if r.status_code != 200:
        raise FalloVoz(f"{modelo} (interactions) HTTP {r.status_code}: {r.text[:300]}")
    mime, datos = _buscar_audio(r.json())
    if not datos:
        raise FalloVoz(f"{modelo} (interactions): respuesta sin audio")
    return _a_wav(mime, datos)


def _gemini_generate(modelo, tanda):
    voces = sorted({t["voz"] for t in tanda["turnos"]})
    if len(voces) > 1:
        texto = (f"{config.ESTILO_VOZ}\n\nLee esta conversación entre {_id('A')} y {_id('B')}, tal cual:\n\n"
                 + "\n".join(f"{_id(t['voz'])}: {t['texto']}" for t in tanda["turnos"]))
        speech = {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
            {"speaker": _id(v), "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": config.LOCUTORES[v]["gemini"]}}}
            for v in voces]}}
    else:
        texto = f"{config.ESTILO_VOZ}\n\nLee en voz alta, tal cual:\n\n" + " ".join(t["texto"] for t in tanda["turnos"])
        speech = {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": config.LOCUTORES[voces[0]]["gemini"]}}}
    cuerpo = {"contents": [{"parts": [{"text": texto}]}],
              "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": speech}}
    r = requests.post(URL_GENERATE.format(modelo=modelo), json=cuerpo, headers=_cabeceras(), timeout=300)
    if r.status_code != 200:
        raise FalloVoz(f"{modelo} (generate) HTTP {r.status_code}: {r.text[:300]}")
    mime, datos = _buscar_audio(r.json())
    if not datos:
        raise FalloVoz(f"{modelo} (generate): respuesta sin audio")
    return _a_wav(mime, datos)


def _llamada(via, modelo, tanda):
    return (_gemini_interactions if via == "interactions" else _gemini_generate)(modelo, tanda)


def _razonable(wav, tanda):
    """¿Dura lo que debería? (detecta audios cortados o con divagaciones)."""
    seg = duracion_wav(wav)
    palabras = sum(util.palabras(t["texto"]) for t in tanda["turnos"])
    esperado = max(1.5, palabras / 2.8)      # ~170 palabras por minuto en conversación
    return 0.5 * esperado <= seg <= 2.0 * esperado + 3, seg, esperado


def _espera(msg):
    m = re.search(r'"retryDelay"\s*:\s*"(\d+)', msg or "")
    return min(75, int(m.group(1)) + 2) if m else 30


def sintetizar_gemini(lista):
    if not os.environ.get("GEMINI_API_KEY"):
        raise FalloVoz("Falta el secreto GEMINI_API_KEY")
    # se prueba el modelo con la primera tanda que tenga las dos voces (así se valida el modo conversación)
    primera = next((i for i, t in enumerate(lista) if len({x["voz"] for x in t["turnos"]}) > 1), 0)
    elegido, errores, audios = None, [], [None] * len(lista)
    for via, modelo in config.MODELOS_VOZ:
        try:
            wav = _llamada(via, modelo, lista[primera])
            ok, seg, esp = _razonable(wav, lista[primera])
            if not ok:
                raise FalloVoz(f"{modelo}: duración rara ({seg:.0f}s, esperaba ~{esp:.0f}s)")
            elegido, audios[primera] = (via, modelo), wav
            util.log(f"Voz Gemini: {modelo} ({via})")
            break
        except Exception as e:
            errores.append(str(e)[:300])
    if not elegido:
        raise FalloVoz("Ningún modelo de voz de Gemini respondió: " + " | ".join(errores))
    for n, tanda in enumerate(lista):
        if audios[n] is not None:
            continue
        ultimo = None
        for intento in range(4):
            try:
                time.sleep(2)
                wav = _llamada(*elegido, tanda)
                ok, seg, esp = _razonable(wav, tanda)
                if not ok:
                    raise FalloVoz(f"duración rara en la tanda {n + 1} ({seg:.0f}s, esperaba ~{esp:.0f}s)")
                audios[n] = wav
                break
            except Exception as e:
                ultimo = str(e)
                time.sleep(_espera(ultimo) if ("429" in ultimo or "RESOURCE_EXHAUSTED" in ultimo) else 5 * (intento + 1))
        else:
            raise FalloVoz(f"Tanda {n + 1} de {len(lista)}: {ultimo[:300] if ultimo else 'sin respuesta'}")
    return audios, f"Gemini · {elegido[1]}"


# ---------------------------------------------------------------- Edge
async def _edge_uno(texto, voz, ruta):
    import edge_tts
    await edge_tts.Communicate(texto, voz, rate=config.EDGE_VELOCIDAD).save(ruta)


def sintetizar_edge(lista, carpeta):
    from pydub import AudioSegment
    audios = []
    for n, tanda in enumerate(lista, 1):
        total = None
        for k, t in enumerate(tanda["turnos"], 1):
            ruta = os.path.join(carpeta, f"edge_{n:02d}_{k:02d}.mp3")
            for intento in range(3):
                try:
                    asyncio.run(_edge_uno(t["texto"], config.LOCUTORES[t["voz"]]["edge"], ruta))
                    seg = AudioSegment.from_file(ruta).set_channels(1).set_frame_rate(24000)
                    break
                except Exception as e:
                    if intento == 2:
                        raise FalloVoz(f"Edge falló en la tanda {n}: {e}")
                    time.sleep(4 * (intento + 1))
            total = seg if total is None else total + AudioSegment.silent(duration=220, frame_rate=24000) + seg
        b = io.BytesIO()
        total.export(b, format="wav")
        audios.append(b.getvalue())
    return audios, "Edge · " + " + ".join(sorted({v["edge"] for v in config.LOCUTORES.values()}))


# ---------------------------------------------------------------- todo junto
def sintetizar(segmentos, carpeta):
    """Devuelve (unidades, motor, avisos). Cada unidad: {'bloque', 'wav', 'palabras', 'segundos'}."""
    lista = tandas(segmentos)
    avisos = []
    audios = motor = None
    if config.MOTOR_VOZ != "edge":
        try:
            audios, motor = sintetizar_gemini(lista)
        except Exception as e:
            avisos.append(f"Voz de Gemini no disponible, uso Edge para todo el episodio: {str(e)[:400]}")
            util.log(avisos[-1])
    if audios is None:
        audios, motor = sintetizar_edge(lista, carpeta)
    unidades = [{"bloque": t["bloque"], "wav": a, "segundos": duracion_wav(a),
                 "palabras": sum(util.palabras(x["texto"]) for x in t["turnos"]),
                 "voces": "".join(sorted({x["voz"] for x in t["turnos"]}))}
                for t, a in zip(lista, audios)]
    return unidades, motor, avisos
