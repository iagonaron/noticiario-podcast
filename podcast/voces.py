"""Pone voz al guion.

1. Gemini (plan gratuito): se busca el primer modelo de voz que responda y se usa
   ese mismo para todo el episodio, para que las voces no cambien a mitad.
2. Si Gemini falla en cualquier trozo (cupo agotado, error, audio cortado), el episodio
   ENTERO se hace con Edge (voces de Microsoft), para que suene coherente. El pódcast llega igual.
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


def trocear(texto, maximo=config.VOZ_MAX_CARACTERES):
    """Parte el texto en trozos de como mucho `maximo` caracteres, por frases."""
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
    rate = 24000
    m = re.search(r"rate=(\d+)", mime or "")
    if m:
        rate = int(m.group(1))
    return pcm_a_wav(datos, rate)


# ---------------------------------------------------------------- Gemini
def _cabeceras():
    return {"x-goog-api-key": os.environ.get("GEMINI_API_KEY", ""), "Content-Type": "application/json"}


def _gemini_interactions(modelo, texto, voz, estilo):
    cuerpo = {
        "model": modelo,
        "input": [{"type": "user_input", "content": [{
            "type": "text", "text": texto,
            "annotations": [{"type": "speech_metadata", "style": estilo}],
        }]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voz}]},
    }
    r = requests.post(URL_INTERACTIONS, json=cuerpo, headers=_cabeceras(), timeout=300)
    if r.status_code != 200:
        raise FalloVoz(f"{modelo} (interactions) HTTP {r.status_code}: {r.text[:300]}")
    mime, datos = _buscar_audio(r.json())
    if not datos:
        raise FalloVoz(f"{modelo} (interactions): respuesta sin audio")
    return _a_wav(mime, datos)


def _gemini_generate(modelo, texto, voz, estilo):
    cuerpo = {
        "contents": [{"parts": [{"text": f"{estilo}\n\nLee en voz alta, tal cual, este texto:\n\n{texto}"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}},
        },
    }
    r = requests.post(URL_GENERATE.format(modelo=modelo), json=cuerpo, headers=_cabeceras(), timeout=300)
    if r.status_code != 200:
        raise FalloVoz(f"{modelo} (generate) HTTP {r.status_code}: {r.text[:300]}")
    mime, datos = _buscar_audio(r.json())
    if not datos:
        raise FalloVoz(f"{modelo} (generate): respuesta sin audio")
    return _a_wav(mime, datos)


def _llamada_gemini(via, modelo, texto, locutor):
    f = _gemini_interactions if via == "interactions" else _gemini_generate
    return f(modelo, texto, locutor["gemini"], locutor["estilo"])


def _audio_razonable(wav, texto):
    """¿Dura lo que debería? (detecta audios cortados o con divagaciones)."""
    seg = duracion_wav(wav)
    esperado = max(1.5, util.palabras(texto) / 2.6)      # ~156 palabras por minuto
    return 0.5 * esperado <= seg <= 2.0 * esperado + 3, seg, esperado


def _espera(msg):
    m = re.search(r'"retryDelay"\s*:\s*"(\d+)', msg or "")
    return min(75, int(m.group(1)) + 2) if m else 30


def sintetizar_gemini(trozos):
    """trozos: [(texto, clave_locutor)] → lista de WAV (bytes). Lanza FalloVoz si no puede con todos."""
    if not os.environ.get("GEMINI_API_KEY"):
        raise FalloVoz("Falta el secreto GEMINI_API_KEY")
    elegido, errores = None, []
    # 1) elegir el primer modelo que funcione, con el primer trozo
    texto0, loc0 = trozos[0]
    for via, modelo in config.MODELOS_VOZ:
        try:
            wav = _llamada_gemini(via, modelo, texto0, config.LOCUTORES[loc0])
            ok, seg, esp = _audio_razonable(wav, texto0)
            if not ok:
                raise FalloVoz(f"{modelo}: duración rara ({seg:.0f}s, esperaba ~{esp:.0f}s)")
            elegido = (via, modelo)
            salida = [wav]
            util.log(f"Voz Gemini: {modelo} ({via})")
            break
        except Exception as e:
            errores.append(str(e)[:300])
    if not elegido:
        raise FalloVoz("Ningún modelo de voz de Gemini respondió: " + " | ".join(errores))
    # 2) el resto de trozos, con el mismo modelo
    for n, (texto, loc) in enumerate(trozos[1:], 2):
        ultimo = None
        for intento in range(4):
            try:
                time.sleep(3)
                wav = _llamada_gemini(*elegido, texto, config.LOCUTORES[loc])
                ok, seg, esp = _audio_razonable(wav, texto)
                if not ok:
                    raise FalloVoz(f"duración rara en el trozo {n} ({seg:.0f}s, esperaba ~{esp:.0f}s)")
                salida.append(wav)
                break
            except Exception as e:
                ultimo = str(e)
                if "429" in ultimo or "RESOURCE_EXHAUSTED" in ultimo:
                    time.sleep(_espera(ultimo))
                else:
                    time.sleep(5 * (intento + 1))
        else:
            raise FalloVoz(f"Trozo {n} de {len(trozos)}: {ultimo[:300] if ultimo else 'sin respuesta'}")
    return salida, f"Gemini · {elegido[1]}"


# ---------------------------------------------------------------- Edge
async def _edge_uno(texto, voz, ruta):
    import edge_tts
    com = edge_tts.Communicate(texto, voz, rate=config.EDGE_VELOCIDAD)
    await com.save(ruta)


def sintetizar_edge(trozos, carpeta):
    from pydub import AudioSegment
    salida = []
    for n, (texto, loc) in enumerate(trozos, 1):
        ruta = os.path.join(carpeta, f"edge_{n:02d}.mp3")
        ultimo = None
        for intento in range(3):
            try:
                asyncio.run(_edge_uno(texto, config.LOCUTORES[loc]["edge"], ruta))
                seg = AudioSegment.from_file(ruta)
                b = io.BytesIO()
                seg.set_channels(1).set_frame_rate(24000).export(b, format="wav")
                salida.append(b.getvalue())
                break
            except Exception as e:
                ultimo = e
                time.sleep(4 * (intento + 1))
        else:
            raise FalloVoz(f"Edge falló en el trozo {n}: {ultimo}")
    return salida, "Edge · " + " + ".join(sorted({config.LOCUTORES[l]["edge"] for _, l in trozos}))


# ---------------------------------------------------------------- todo junto
def sintetizar(segmentos, carpeta):
    """Devuelve (audios, motor, avisos). `audios` va en paralelo con los trozos devueltos."""
    trozos, indice = [], []
    for i, s in enumerate(segmentos):
        for t in trocear(s["texto"]):
            trozos.append((t, s["voz"]))
            indice.append(i)
    avisos = []
    if config.MOTOR_VOZ != "edge":
        try:
            audios, motor = sintetizar_gemini(trozos)
            return audios, indice, motor, avisos
        except Exception as e:
            avisos.append(f"Voz de Gemini no disponible, uso Edge para todo el episodio: {str(e)[:400]}")
            util.log(avisos[-1])
    audios, motor = sintetizar_edge(trozos, carpeta)
    return audios, indice, motor, avisos
