"""Corta en turnos el audio de una tanda de UNA sola voz (todas las frases de Lucía, o de Martín,
dichas seguidas), para luego montar el diálogo intercalándolas.

1. Una transcripción automática con tiempos por palabra (faster-whisper, en el propio servidor de
   GitHub, sin gastar cupo de nada) dice dónde termina un turno y empieza el siguiente.
2. El corte se hace en el silencio real más largo de esa zona (nunca en mitad de una palabra).
   Si la transcripción falla o no está, la posición esperada se estima por el número de palabras.
3. Se comprueba que cada trozo dure lo razonable para sus palabras; si no, se avisa con ErrorAlineado.
"""
import difflib
import io
import math
import re
import subprocess
import unicodedata
import wave

import numpy as np

from . import config, util

SR = 16000          # frecuencia de trabajo para el análisis
PASO = 0.01         # resolución de la envolvente (10 ms)
_MODELO = {"m": None, "error": None}


class ErrorAlineado(Exception):
    pass


# ---------------------------------------------------------------- utilidades
def norma(texto):
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9ñ]+", t)


def a_mono16k(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        datos = w.readframes(n)
    if sw != 2:
        raise ErrorAlineado("WAV que no es de 16 bits")
    x = np.frombuffer(datos, np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        t_orig = np.arange(len(x)) / sr
        t_new = np.arange(int(len(x) * SR / sr)) / SR
        x = np.interp(t_new, t_orig, x).astype(np.float32)
    return x


def envolvente_db(x, sr=SR):
    n = int(sr * PASO)
    k = len(x) // n
    if k == 0:
        return np.array([-100.0])
    tramos = x[:k * n].reshape(k, n)
    rms = np.sqrt((tramos ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9)


def silencios(env, minimo_s=0.12):
    """Tramos de silencio (inicio_s, fin_s, duración_s) con un umbral que se adapta al audio."""
    suelo = np.percentile(env, 5)
    voz = np.percentile(env, 70)
    umbral = suelo + max(6.0, (voz - suelo) * 0.25)
    bajo = env < umbral
    out, ini = [], None
    for i, b in enumerate(np.append(bajo, False)):
        if b and ini is None:
            ini = i
        elif not b and ini is not None:
            d = (i - ini) * PASO
            if d >= minimo_s:
                out.append((ini * PASO, i * PASO, d))
            ini = None
    return out, umbral


# ---------------------------------------------------------------- transcripción
def _modelo():
    if _MODELO["m"] is None and _MODELO["error"] is None:
        try:
            from faster_whisper import WhisperModel
            _MODELO["m"] = WhisperModel(config.WHISPER_MODELO, device="cpu", compute_type="int8")
        except Exception as e:                       # sin whisper se sigue con la estimación
            _MODELO["error"] = f"{type(e).__name__}: {e}"[:200]
            util.log(f"Alineado sin transcripción: {_MODELO['error']}")
    return _MODELO["m"]


def _palabras(x):
    m = _modelo()
    if m is None:
        return []
    segs, _ = m.transcribe(x, language="es", word_timestamps=True, beam_size=1, vad_filter=False,
                           condition_on_previous_text=False)
    out = []
    for s in segs:
        for w in (s.words or []):
            for tok in norma(w.word):
                out.append((tok, float(w.start), float(w.end)))
    return out


# ---------------------------------------------------------------- cortes
def _anclas(textos, rec):
    """Para cada turno, (inicio, fin) de sus palabras reconocidas, o None si no se reconoció."""
    exp, dueno = [], []
    for i, t in enumerate(textos):
        toks = norma(t)
        exp += toks
        dueno += [i] * len(toks)
    if not rec or not exp:
        return [None] * len(textos), 0.0
    sm = difflib.SequenceMatcher(None, exp, [r[0] for r in rec], autojunk=False)
    mapa = {}
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            mapa[a + k] = b + k
    anclas = []
    for i in range(len(textos)):
        idx = [j for j in range(len(exp)) if dueno[j] == i and j in mapa]
        if len(idx) >= 1:
            anclas.append((rec[mapa[idx[0]]][1], rec[mapa[idx[-1]]][2]))
        else:
            anclas.append(None)
    return anclas, len(mapa) / max(1, len(exp))


def _esperados(textos, anclas, ini_voz, fin_voz):
    """Posición esperada de cada frontera entre turnos: por la transcripción si la hay; si no,
    repartiendo el tiempo según las palabras entre las anclas conocidas."""
    pal = [max(1, len(norma(t))) for t in textos]
    n = len(textos)
    fronteras = [None] * (n - 1)
    fiables = [False] * (n - 1)
    for k in range(n - 1):
        a, b = anclas[k], anclas[k + 1]
        if a and b and b[0] > a[1] - 0.05:
            fronteras[k] = (a[1] + b[0]) / 2
            fiables[k] = True
    # puntos fijos conocidos (posición del inicio del turno k en segundos)
    fijos = {0: ini_voz, n: fin_voz}
    for k in range(n - 1):
        if fronteras[k] is not None:
            fijos[k + 1] = fronteras[k]
    claves = sorted(fijos)
    acum = np.concatenate([[0], np.cumsum(pal)])
    for k in range(n - 1):
        if fronteras[k] is None:
            i = max(c for c in claves if c <= k + 1)
            j = min(c for c in claves if c >= k + 1)
            if i == j:
                fronteras[k] = fijos[i]
            else:
                frac = (acum[k + 1] - acum[i]) / max(1e-9, acum[j] - acum[i])
                fronteras[k] = fijos[i] + frac * (fijos[j] - fijos[i])
    return list(zip(fronteras, fiables))


def _elegir(esperados, candidatos, dur):
    """Elige, en orden, un silencio candidato para cada frontera: cerca de lo esperado y, a igualdad,
    el más largo (programación dinámica)."""
    n, m = len(esperados), len(candidatos)
    if m < n:
        raise ErrorAlineado(f"pocos silencios ({m}) para {n} cortes")
    INF = float("inf")
    coste = [[INF] * m for _ in range(n)]
    previo = [[-1] * m for _ in range(n)]

    def c(k, j):
        centro, largo = candidatos[j]
        pos, fiable = esperados[k]
        # con la transcripción, el corte va al silencio de esa misma pausa; sin ella, al silencio
        # largo más cercano a lo que tocaría por número de palabras
        sigma, peso = (0.25, 1.0) if fiable else (max(1.0, dur * 0.03), 2.0)
        return ((centro - pos) / sigma) ** 2 - peso * math.log(max(largo, 0.05) / 0.15)

    for j in range(m):
        coste[0][j] = c(0, j)
    for k in range(1, n):
        mejor, arg = INF, -1
        for j in range(m):
            if j - 1 >= 0 and coste[k - 1][j - 1] < mejor:
                mejor, arg = coste[k - 1][j - 1], j - 1
            if mejor < INF:
                coste[k][j] = mejor + c(k, j)
                previo[k][j] = arg
    j = min(range(m), key=lambda q: coste[n - 1][q])
    if coste[n - 1][j] == INF:
        raise ErrorAlineado("no hay un reparto ordenado de los cortes")
    elegidos = [j]
    for k in range(n - 1, 0, -1):
        j = previo[k][j]
        elegidos.append(j)
    elegidos.reverse()
    return [candidatos[q][0] for q in elegidos]


def cortes(wav_bytes, textos):
    """Devuelve [(inicio_s, fin_s)] para cada texto (turno) dentro del audio de la tanda, y un
    resumen técnico. Lanza ErrorAlineado si el resultado no es fiable."""
    x = a_mono16k(wav_bytes)
    dur = len(x) / SR
    env = envolvente_db(x)
    sil, _ = silencios(env)
    # dónde empieza y acaba la voz
    voz_ini = sil[0][1] if sil and sil[0][0] <= 0.02 else 0.0
    voz_fin = sil[-1][0] if sil and sil[-1][1] >= dur - 0.05 else dur
    if len(textos) == 1:
        return [(max(0.0, voz_ini - 0.05), min(dur, voz_fin + 0.12))], "un solo turno"
    rec = _palabras(x)
    anclas, cobertura = _anclas(textos, rec)
    esperados = _esperados(textos, anclas, voz_ini, voz_fin)
    candidatos = [((a + b) / 2, d) for a, b, d in sil if voz_ini + 0.2 < (a + b) / 2 < voz_fin - 0.2]
    # si la transcripción marca una frontera sin silencio claro cerca, se ofrece ese punto también
    for pos, fiable in esperados:
        if fiable and not any(abs(cc - pos) <= 0.15 for cc, _ in candidatos):
            candidatos.append((pos, 0.1))
    candidatos.sort()
    puntos = _elegir(esperados, candidatos, dur)
    limites = [max(0.0, voz_ini - 0.05)] + puntos + [min(dur, voz_fin + 0.12)]
    tramos = [(limites[i], limites[i + 1]) for i in range(len(textos))]
    # comprobación: cada turno, una duración razonable para sus palabras
    for (a, b), t in zip(tramos, textos):
        palabras = max(1, len(norma(t)))
        esperado = palabras / 2.7
        if not (0.35 * esperado - 0.4 <= (b - a) <= 2.6 * esperado + 1.2):
            raise ErrorAlineado(f"un turno de {palabras} palabras quedó en {b - a:.1f}s")
    resumen = (f"{len(textos)} turnos · transcripción {'sí' if rec else 'no'} ({cobertura:.0%} de palabras) · "
               f"{len(candidatos)} silencios")
    return tramos, resumen


def recortar(wav_bytes, inicio, fin):
    """WAV del tramo [inicio, fin] (en segundos) del audio original, sin tocar la calidad."""
    with wave.open(io.BytesIO(wav_bytes)) as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        w.setpos(int(inicio * sr))
        datos = w.readframes(max(0, int((fin - inicio) * sr)))
    b = io.BytesIO()
    with wave.open(b, "wb") as o:
        o.setnchannels(ch)
        o.setsampwidth(sw)
        o.setframerate(sr)
        o.writeframes(datos)
    return b.getvalue()
