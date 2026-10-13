"""Monta el programa como un informativo de radio: una música de fondo suena durante todo el
programa; arranca arriba 3-4 segundos, baja cuando empiezan a hablar, sube 2-3 segundos entre una
noticia y la siguiente y vuelve a bajar, y al final sube y se apaga.
Después iguala el volumen a nivel de pódcast (-16 LUFS) y lo guarda en MP3 para el iPhone.

La música sale de la carpeta privada del pódcast en Dropbox («musica/fondo.mp3», una pista de
biblioteca libre). Si no está, se usan la entrada y el cierre antiguos o, sin nada, solo pausas.
"""
import io
import json
import re
import subprocess

import numpy as np
from pydub import AudioSegment
from pydub.silence import detect_leading_silence

from . import config

PIEZAS = ("fondo", "intro", "transicion", "cierre")
SR = 44100
VOZ_DBFS = -19.0
MUSICA_ARRIBA = -3.0       # dB respecto a la voz cuando la música suena sola
MUSICA_FONDO = -21.0       # dB respecto a la voz mientras hablan («de fondo»)
ENTRADA_MS = 3500          # música sola al empezar
PAUSA_TURNO_MS = 300       # entre turnos de la misma noticia
PAUSA_RAPIDO_MS = 450      # entre las frases de «lo rápido» (cumpleaños, agenda, tiempo)
RAFAGA_NOTICIA_MS = 2500   # entre noticias: la música sube
RAFAGA_BLOQUE_MS = 3200    # entre bloques (titulares, local, interés…)
SALIDA_MS = 6000           # música al final: sube y se apaga
SUBIDA_MS = 450            # rampa de subida de la música al acabar de hablar
BAJADA_MS = 600            # rampa de bajada: termina justo cuando entra la voz
CRUCE_MS = 1500            # fundido al repetir la pista


def _mono(seg):
    return seg.set_frame_rate(SR).set_channels(1).set_sample_width(2)


def cargar_musica(desde_dropbox=None):
    """desde_dropbox: {'fondo': bytes, ...} con lo que haya en la carpeta «musica» de Dropbox."""
    return {p: _mono(AudioSegment.from_file(io.BytesIO(d))) for p, d in (desde_dropbox or {}).items() if d}


def _recortar(seg):
    """Quita el silencio de los extremos (dejando un margen mínimo)."""
    umbral = seg.max_dBFS - 42 if seg.max_dBFS > -90 else -60
    ini = max(0, detect_leading_silence(seg, silence_threshold=umbral) - 30)
    fin = max(0, detect_leading_silence(seg.reverse(), silence_threshold=umbral) - 60)
    return seg[ini:len(seg) - fin] if len(seg) - fin > ini else seg


def _nivelar(seg, objetivo=VOZ_DBFS):
    return seg if seg.dBFS == float("-inf") else seg.apply_gain(objetivo - seg.dBFS)


def _a_numpy(seg):
    return np.array(seg.get_array_of_samples(), dtype=np.float32) / 32768.0


def _cama(pista, total_ms):
    """La pista, con su principio y su final naturales, alargada repitiendo la parte central."""
    largo = len(pista)
    a = min(8000, largo // 4)
    b = largo - min(6000, largo // 5)
    final = pista[b:]
    if total_ms <= largo:
        return pista[:max(0, total_ms - len(final))].append(final, crossfade=min(CRUCE_MS, len(final) // 2))
    cama = pista[:b]
    medio = pista[a:b]
    while len(cama) < total_ms - len(final) + CRUCE_MS:
        cama = cama.append(medio, crossfade=CRUCE_MS)
    cama = cama[:total_ms - len(final) + CRUCE_MS]
    return cama.append(final, crossfade=CRUCE_MS)


def _envolvente(regiones, total_ms):
    """Ganancia de la música (dB, relativa a «arriba») en cada momento: abajo mientras hablan."""
    abajo = MUSICA_FONDO - MUSICA_ARRIBA
    puntos = [(0, -30.0), (180, 0.0)]
    for ini, fin in regiones:
        puntos += [(ini - BAJADA_MS, 0.0), (ini, abajo), (fin, abajo), (fin + SUBIDA_MS, 0.0)]
    puntos += [(total_ms - 2600, 0.0), (total_ms, -40.0)]
    # por si dos rampas se pisan, se respeta el orden en el tiempo
    limpios = []
    for t, g in puntos:
        t = max(0, min(total_ms, t))
        if limpios and t <= limpios[-1][0]:
            t = limpios[-1][0] + 1
        limpios.append((t, g))
    t, g = zip(*limpios)
    return np.array(t, dtype=np.float64), np.array(g, dtype=np.float64)


def montar(piezas, musica, ruta_wav):
    """piezas: lista ordenada de {'wav': bytes, 'bloque': str, 'noticia': int}. Devuelve la duración (s)."""
    fondo = musica.get("fondo")
    voces = [_nivelar(_recortar(_mono(AudioSegment.from_file(io.BytesIO(p["wav"]), format="wav")))) for p in piezas]

    # 1) dónde va cada trozo de voz
    pos = ENTRADA_MS if fondo else 300
    colocados, anterior = [], None
    for p, voz in zip(piezas, voces):
        bloque = "rapido" if p.get("bloque") == "apertura" else p.get("bloque")
        if anterior is not None:
            if bloque != anterior[0]:
                pos += RAFAGA_BLOQUE_MS if fondo else 1200
            elif p.get("noticia") != anterior[1]:
                pos += RAFAGA_NOTICIA_MS if fondo else 900
            else:
                pos += PAUSA_RAPIDO_MS if bloque == "rapido" else PAUSA_TURNO_MS
        colocados.append((pos, voz))
        pos += len(voz)
        anterior = (bloque, p.get("noticia"))
    total = pos + (SALIDA_MS if fondo else 700)

    # 2) pista de voz
    n = int(total * SR / 1000) + SR
    mezcla = np.zeros(n, dtype=np.float32)
    regiones = []
    for ini, voz in colocados:
        x = _a_numpy(voz)
        k = int(ini * SR / 1000)
        mezcla[k:k + len(x)] += x[:max(0, n - k)]
        fin = ini + len(voz)
        if regiones and ini - regiones[-1][1] < 1200:      # pausas cortas: la música sigue abajo
            regiones[-1] = (regiones[-1][0], fin)
        else:
            regiones.append((ini, fin))

    # 3) música: cama continua con su envolvente
    if fondo:
        cama = _cama(fondo.apply_gain((VOZ_DBFS + MUSICA_ARRIBA) - fondo.dBFS), total)
        m = _a_numpy(cama)[:n]
        t, g = _envolvente(regiones, total)
        ms = np.arange(len(m)) * 1000.0 / SR
        m *= np.power(10.0, np.interp(ms, t, g) / 20.0).astype(np.float32)
        mezcla[:len(m)] += m
    else:
        intro, cierre = musica.get("intro"), musica.get("cierre")
        if intro:
            x = _a_numpy(intro.apply_gain((VOZ_DBFS - 4) - intro.dBFS))[:n]
            mezcla[:len(x)] += x
        if cierre:
            x = _a_numpy(cierre.apply_gain((VOZ_DBFS - 4) - cierre.dBFS).fade_out(2500))
            k = int(max(0, total - 700) * SR / 1000)
            extra = k + len(x) - n
            if extra > 0:
                mezcla = np.concatenate([mezcla, np.zeros(extra, dtype=np.float32)])
            mezcla[k:k + len(x)] += x

    pico = float(np.max(np.abs(mezcla))) or 1.0
    if pico > 0.99:
        mezcla *= 0.99 / pico
    datos = (mezcla * 32767).astype(np.int16).tobytes()
    AudioSegment(datos, frame_rate=SR, sample_width=2, channels=1).export(ruta_wav, format="wav")
    return len(mezcla) / SR


def a_mp3(ruta_wav, ruta_mp3, etiquetas):
    """Iguala el volumen en dos pasadas (loudnorm) y codifica a MP3 con etiquetas."""
    medir = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", ruta_wav, "-af",
         f"loudnorm=I={config.SONORIDAD_LUFS}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True)
    filtro = f"loudnorm=I={config.SONORIDAD_LUFS}:TP=-1.5:LRA=11"
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", medir.stderr, re.S)
    if m:
        j = json.loads(m.group(0))
        filtro += (f":measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}"
                   f":measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", ruta_wav, "-af", filtro,
           "-ar", str(SR), "-ac", "1", "-c:a", "libmp3lame", "-b:a", config.MP3_KBPS, "-id3v2_version", "3"]
    for k, v in etiquetas.items():
        cmd += ["-metadata", f"{k}={v}"]
    subprocess.run(cmd + [ruta_mp3], check=True)
