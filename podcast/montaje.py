"""Monta el programa: sintonía, conversación y cierre musical.
Al final iguala el volumen a nivel de pódcast (-16 LUFS) y lo guarda en MP3 para el iPhone.

La música sale de la carpeta privada del pódcast en Dropbox (/musica: intro, transicion y cierre,
en .mp3 o .wav). Si no hay, el programa va sin música.
"""
import io
import json
import re
import subprocess

from pydub import AudioSegment

from . import config

PIEZAS = ("intro", "transicion", "cierre")
SR = 44100
VOZ_DBFS = -19.0


def _mono(seg):
    return seg.set_frame_rate(SR).set_channels(1).set_sample_width(2)


def cargar_musica(desde_dropbox=None):
    """desde_dropbox: {'intro': bytes, ...} con lo que haya en la carpeta «musica» de Dropbox."""
    return {p: _mono(AudioSegment.from_file(io.BytesIO(d))) for p, d in (desde_dropbox or {}).items() if d}


def _nivelar(seg, objetivo=VOZ_DBFS):
    return seg if seg.dBFS == float("-inf") else seg.apply_gain(objetivo - seg.dBFS)


def _silencio(ms):
    return AudioSegment.silent(duration=ms, frame_rate=SR)


def montar(unidades, musica, ruta_wav):
    intro, trans, cierre = (musica.get(p) for p in PIEZAS)
    voces = [_nivelar(_mono(AudioSegment.from_file(io.BytesIO(u["wav"]), format="wav"))) for u in unidades]

    if intro:
        # la sintonía suena y, mientras se apaga, entra la primera voz
        programa = intro.apply_gain((VOZ_DBFS - 4) - intro.dBFS)
        pos = max(0, len(programa) - 2800)
    else:
        programa, pos = _silencio(250), 250

    anterior = None
    for u, voz in zip(unidades, voces):
        if anterior is None:
            pieza = voz
        elif u["bloque"] == anterior:
            pieza = _silencio(260) + voz
        elif trans:
            pieza = _silencio(250) + trans.apply_gain((VOZ_DBFS - 6) - trans.dBFS) + _silencio(200) + voz
        else:
            pieza = _silencio(650) + voz
        fin = pos + len(pieza)
        if fin > len(programa):
            programa += _silencio(fin - len(programa))
        programa = programa.overlay(pieza, position=pos)
        pos = fin
        anterior = u["bloque"]

    programa = programa[:pos] + _silencio(500)
    if cierre:
        programa += cierre.apply_gain((VOZ_DBFS - 4) - cierre.dBFS).fade_out(2500)
    programa += _silencio(500)
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
