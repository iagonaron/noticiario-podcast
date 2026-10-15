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
try:                                   # la transcripción escribe las cifras con números y el guion, con letras
    from num2words import num2words as _num2words
except Exception:                      # pragma: no cover
    _num2words = None


def _fichas(texto):
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9ñ]+", t)


def norma(texto):
    """Palabras en minúsculas, sin tildes ni signos, y las cifras dichas con letras («2026» → dos mil veintiseis)."""
    salida = []
    for tok in _fichas(texto):
        if _num2words and tok.isdigit() and len(tok) <= 9:
            try:
                salida += _fichas(_num2words(int(tok), lang="es"))
                continue
            except Exception:
                pass
        salida.append(tok)
    return salida


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


_ULTIMAS = {"palabras": []}


def se_oye(frase):
    """¿Aparece esa frase (p. ej. «long pause») en lo último que se transcribió?"""
    toks = norma(frase)
    oidas = [w for w, _, _ in _ULTIMAS["palabras"]]
    return any(oidas[i:i + len(toks)] == toks for i in range(len(oidas) - len(toks) + 1)) if toks else False


def _palabras(x):
    m = _modelo()
    if m is None:
        _ULTIMAS["palabras"] = []
        return []
    segs, _ = m.transcribe(x, language="es", word_timestamps=True, beam_size=1, vad_filter=False,
                           condition_on_previous_text=False)
    out = []
    for s in segs:
        for w in (s.words or []):
            for tok in norma(w.word):
                out.append((tok, float(w.start), float(w.end)))
    _ULTIMAS["palabras"] = out
    return out


# ---------------------------------------------------------------- cortes
def _coincidencias(textos, rec):
    """Para cada turno, lo que se reconoció de él: {'ini': inicio de su primera palabra reconocida,
    'fin': final de la última, 'n': palabras reconocidas}, o None si no se reconoció nada."""
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
        # una palabra corta suelta («no», «y», «de») que coincide sola suele ser de otro sitio
        if n >= 2 or (n == 1 and len(exp[a]) >= 4):
            for k in range(n):
                mapa[a + k] = b + k
    salida = []
    for i in range(len(textos)):
        suyas = [j for j in range(len(exp)) if dueno[j] == i]
        idx = [j for j in suyas if j in mapa]
        # se descartan coincidencias sueltas de una sola palabra corta (suelen ser «y», «de»…)
        if len(idx) >= 2 or (len(idx) == 1 and len(exp[idx[0]]) >= 4):
            # letras del turno que quedan antes de la primera palabra reconocida y después de la última
            # (una coletilla como «¿eh?» o una cifra que no se reconoció): también son de este turno
            antes = sum(len(exp[j]) + 1 for j in suyas if j < idx[0])
            despues = sum(len(exp[j]) + 1 for j in suyas if j > idx[-1])
            salida.append({"ini": rec[mapa[idx[0]]][1], "fin": rec[mapa[idx[-1]]][2], "n": len(idx),
                           "letras": sum(len(exp[j]) + 1 for j in idx[0:1] + [j for j in suyas if idx[0] < j <= idx[-1]]),
                           "resto_ini": antes, "resto_fin": despues})
        else:
            salida.append(None)
    return salida, len(mapa) / max(1, len(exp))


def _ritmo(turnos, env, umbral):
    """Letras por segundo de voz (sin contar las pausas) de esta voz, medidas en los propios turnos
    reconocidos; por defecto, 16."""
    datos = []
    for t in turnos:
        if t and t["fin"] - t["ini"] > 1.0:
            voz = _voz_entre(env, umbral, t["ini"], t["fin"])
            if voz > 0.5:
                datos.append(t["letras"] / voz)
    return float(np.median(datos)) if len(datos) >= 3 else 16.0


def _voz_entre(env, umbral, a, b):
    """Segundos con voz (envolvente por encima del umbral de silencio) entre a y b."""
    i, j = int(max(0.0, a) / PASO), int(max(0.0, b) / PASO)
    return float((env[i:j] >= umbral).sum()) * PASO if j > i else 0.0


def _frontera(env, umbral, sil, a, b, ritmo):
    """Dónde cortar entre el turno a y el siguiente b (ya reconocidos los dos).

    Entre la última palabra reconocida de a (L) y la primera de b (R) puede quedar voz que no se
    reconoció: el final de a (una coletilla, una cifra…) y el principio de b. Se elige el silencio
    que deja antes la voz que le falta a a y después la que le falta a b y, a igualdad, el más largo.
    Así el «¿eh?» del final de un turno no se va al principio del siguiente."""
    L, R = a["fin"], b["ini"]
    falta_a, falta_b = a["resto_fin"] / ritmo, b["resto_ini"] / ritmo
    dentro = [(s0, s1, d) for s0, s1, d in sil if L - 0.06 <= (s0 + s1) / 2 <= R + 0.06]
    if not dentro:
        lo, hi = L + falta_a * 0.8, R - falta_b * 0.8
        return _punto_mas_bajo(env, lo, hi) if hi > lo else _punto_mas_bajo(env, L, R)

    def coste(s):
        s0, s1, d = s
        antes = _voz_entre(env, umbral, L, s0)
        despues = _voz_entre(env, umbral, s1, R)
        return abs(antes - falta_a) + abs(despues - falta_b) - 0.25 * math.log(max(d, 0.05) / 0.1)

    s0, s1, _ = min(dentro, key=coste)
    return (s0 + s1) / 2


def _punto_mas_bajo(env, a, b):
    i, j = int(max(0, a) / PASO), int(max(a, b) / PASO) + 1
    if j <= i + 1:
        return a
    return (i + int(np.argmin(env[i:j]))) * PASO + PASO / 2


def _interpolar(textos, fijos, ini_voz, fin_voz):
    """Posición estimada de las fronteras que no se pudieron fijar con la transcripción, repartiendo
    el tiempo según las palabras entre las fronteras sí fijadas."""
    pal = [max(1, len(norma(t))) for t in textos]
    n = len(textos)
    puntos = {0: ini_voz, n: fin_voz}
    for k, c in enumerate(fijos):
        if c is not None:
            puntos[k + 1] = c
    claves = sorted(puntos)
    acum = np.concatenate([[0], np.cumsum(pal)])
    salida = []
    for k in range(n - 1):
        if fijos[k] is not None:
            salida.append((fijos[k], True))
            continue
        i = max(c for c in claves if c <= k + 1)
        j = min(c for c in claves if c >= k + 1)
        frac = (acum[k + 1] - acum[i]) / max(1e-9, acum[j] - acum[i])
        salida.append((puntos[i] + frac * (puntos[j] - puntos[i]), False))
    return salida


def _elegir(esperados, candidatos, dur):
    """Elige, en orden, un silencio candidato para cada frontera: las fijadas se quedan donde están;
    las demás, cerca de lo estimado y, a igualdad, el silencio más largo (programación dinámica)."""
    n, m = len(esperados), len(candidatos)
    if m < n:
        raise ErrorAlineado(f"pocos silencios ({m}) para {n} cortes")
    INF = float("inf")
    coste = [[INF] * m for _ in range(n)]
    previo = [[-1] * m for _ in range(n)]

    def c(k, j):
        centro, largo = candidatos[j]
        pos, fiable = esperados[k]
        if fiable:
            return 0.0 if abs(centro - pos) < 0.005 else 1e6
        sigma = max(1.0, dur * 0.03)
        return ((centro - pos) / sigma) ** 2 - 2.0 * math.log(max(largo, 0.05) / 0.15)

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
    if coste[n - 1][j] >= 1e6:
        raise ErrorAlineado("no hay un reparto ordenado de los cortes")
    elegidos = [j]
    for k in range(n - 1, 0, -1):
        j = previo[k][j]
        elegidos.append(j)
    elegidos.reverse()
    return [candidatos[q][0] for q in elegidos]


def cortes(wav_bytes, textos):
    """Devuelve [(inicio_s, fin_s)] para cada texto (turno) dentro del audio de la tanda, y un
    resumen técnico. Lanza ErrorAlineado si el resultado no es fiable.

    Regla principal: entre la última palabra reconocida de un turno y la primera del siguiente,
    el corte va en el silencio más largo (la pausa entre turnos). Así nunca se corta dentro de
    palabras que se sabe de qué turno son."""
    x = a_mono16k(wav_bytes)
    dur = len(x) / SR
    env = envolvente_db(x)
    sil, umbral = silencios(env, minimo_s=0.08)
    voz_ini = sil[0][1] if sil and sil[0][0] <= 0.02 else 0.0
    voz_fin = sil[-1][0] if sil and sil[-1][1] >= dur - 0.05 else dur
    if len(textos) == 1:
        return [(max(0.0, voz_ini - 0.05), min(dur, voz_fin + 0.15))], "un solo turno"
    rec = _palabras(x)
    turnos, cobertura = _coincidencias(textos, rec)
    ritmo = _ritmo(turnos, env, umbral)
    n = len(textos)
    fijos = [None] * (n - 1)
    bordes = 0
    for k in range(n - 1):
        a, b = turnos[k], turnos[k + 1]
        if not (a and b) or b["ini"] < a["fin"] - 0.03:
            continue
        bordes += 1 if (a["resto_fin"] or b["resto_ini"]) else 0
        fijos[k] = _frontera(env, umbral, sil, a, b, ritmo)
    # las fronteras fijadas tienen que ir en orden
    ultimo = -1.0
    for k in range(n - 1):
        if fijos[k] is not None:
            if fijos[k] <= ultimo + 0.2:
                fijos[k] = None
            else:
                ultimo = fijos[k]
    esperados = _interpolar(textos, fijos, voz_ini, voz_fin)
    candidatos = [((s0 + s1) / 2, d) for s0, s1, d in sil if voz_ini + 0.2 < (s0 + s1) / 2 < voz_fin - 0.2]
    candidatos += [(pos, 0.3) for pos, fiable in esperados if fiable]
    candidatos = sorted(set(candidatos))
    puntos = _elegir(esperados, candidatos, dur)
    limites = [max(0.0, voz_ini - 0.05)] + puntos + [min(dur, voz_fin + 0.15)]
    tramos = [(limites[i], limites[i + 1]) for i in range(n)]
    # comprobaciones: duración razonable y que las palabras reconocidas de cada turno caen en su trozo
    for i, ((a, b), t) in enumerate(zip(tramos, textos)):
        palabras = max(1, len(norma(t)))
        esperado = palabras / 2.7
        if not (0.35 * esperado - 0.4 <= (b - a) <= 2.6 * esperado + 1.2):
            raise ErrorAlineado(f"un turno de {palabras} palabras quedó en {b - a:.1f}s")
        # (en los extremos de la tanda no se mira: ahí la transcripción suele dar tiempos imprecisos)
        if turnos[i] and ((i > 0 and turnos[i]["ini"] < a - 0.15) or (i < n - 1 and turnos[i]["fin"] > b + 0.15)):
            raise ErrorAlineado(f"el turno {i + 1} tiene palabras fuera de su trozo")
    resumen = (f"{n} turnos · transcripción {'sí' if rec else 'no'} ({cobertura:.0%} de palabras) · "
               f"{sum(1 for f in fijos if f is not None)}/{n - 1} cortes fijados por la transcripción · "
               f"{bordes} con palabras sin reconocer junto al corte · {ritmo:.0f} letras/s")
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
