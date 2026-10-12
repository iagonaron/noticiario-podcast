"""Monta el programa: sintonía, voces, transiciones, música bajo el tiempo y cierre.
Al final iguala el volumen a nivel de pódcast (-16 LUFS) y lo guarda en MP3 para el iPhone.
"""
import io
import json
import os
import re
import subprocess

from pydub import AudioSegment

from . import config

AQUI = os.path.dirname(os.path.abspath(__file__))
CARPETA_MUSICA = os.path.join(AQUI, "..", "musica")
PIEZAS = ("intro", "transicion", "fondo", "cierre")
SR = 44100
VOZ_DBFS = -19.0


def _mono(seg):
    return seg.set_frame_rate(SR).set_channels(1).set_sample_width(2)


def cargar_musica(desde_dropbox=None):
    """desde_dropbox: {'intro': bytes, ...} con lo que haya en la carpeta «musica» de Dropbox."""
    musica = {}
    for p in PIEZAS:
        datos = (desde_dropbox or {}).get(p)
        if datos:
            musica[p] = _mono(AudioSegment.from_file(io.BytesIO(datos)))
            continue
        for ext in ("mp3", "wav"):
            ruta = os.path.join(CARPETA_MUSICA, f"{p}.{ext}")
            if os.path.exists(ruta):
                musica[p] = _mono(AudioSegment.from_file(ruta))
                break
    return musica


def _nivelar(seg, objetivo=VOZ_DBFS):
    if seg.dBFS == float("-inf"):
        return seg
    return seg.apply_gain(objetivo - seg.dBFS)


def _silencio(ms):
    return AudioSegment.silent(duration=ms, frame_rate=SR)


def _voces_por_segmento(audios, indice, n_segmentos):
    voces = [None] * n_segmentos
    for wav, i in zip(audios, indice):
        trozo = _mono(AudioSegment.from_file(io.BytesIO(wav), format="wav"))
        voces[i] = trozo if voces[i] is None else voces[i] + _silencio(120) + trozo
    return [_nivelar(v) if v is not None else _silencio(10) for v in voces]


def _con_fondo(voz, fondo):
    """La voz del tiempo con la música de fondo muy baja, entrando y saliendo suave."""
    if not fondo:
        return voz
    largo = len(voz) + 1800
    cama = fondo
    while len(cama) < largo:
        cama = cama.append(fondo, crossfade=600)
    cama = cama[:largo]
    cama = cama.apply_gain((VOZ_DBFS - 21) - cama.dBFS).fade_in(900).fade_out(1600)
    return cama.overlay(_silencio(500) + voz)


def montar(segmentos, audios, indice, musica, ruta_wav):
    voces = _voces_por_segmento(audios, indice, len(segmentos))
    intro, trans, fondo, cierre = (musica.get(p) for p in PIEZAS)
    if trans:
        trans = trans.apply_gain(-3)

    # 1) sintonía y, sobre su cola, el saludo
    if intro:
        programa = intro.apply_gain(-2)
        entrada = max(0, len(programa) - 1700)
        programa = programa[:entrada] + programa[entrada:].fade_out(1700)
        pos = entrada
    else:
        programa, pos = _silencio(300), 300

    bloque_anterior, voz_anterior = None, None
    for seg, voz in zip(segmentos, voces):
        bloque = seg["bloque"]
        if bloque_anterior is None:
            pieza = voz
        elif bloque in ("agenda",) or bloque == bloque_anterior:
            pausa = 450 if seg["voz"] != voz_anterior else 300
            pieza = _silencio(pausa) + voz
        else:
            pieza = (_silencio(250) + trans + _silencio(200)) if trans else _silencio(700)
            pieza += (_con_fondo(voz, fondo) if bloque == "tiempo" else voz)
        # se pega a partir de «pos», que puede caer dentro de la sintonía
        fin_necesario = pos + len(pieza)
        if fin_necesario > len(programa):
            programa += _silencio(fin_necesario - len(programa))
        programa = programa.overlay(pieza, position=pos)
        pos = fin_necesario
        bloque_anterior, voz_anterior = bloque, seg["voz"]

    # 2) cierre musical
    programa = programa[:pos] + _silencio(450)
    if cierre:
        programa += cierre.apply_gain(-2).fade_out(1500)
    programa += _silencio(600)
    programa.export(ruta_wav, format="wav")
    return len(programa) / 1000.0


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
