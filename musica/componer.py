"""Compone las sintonías provisionales del pódcast (libres de derechos: están hechas aquí, por código).

    python musica/componer.py      →  musica/intro.mp3, transicion.mp3, fondo.mp3, cierre.mp3

Re mayor, sonido de piano eléctrico, campanitas, colchón suave y un bajo discreto.
Para cambiarlas por las tuyas, deja intro / transicion / fondo / cierre (.mp3 o .wav)
en la carpeta «musica» del pódcast en Dropbox: el robot usa esas si existen.
"""
import os
import subprocess

import numpy as np

SR = 44100
AQUI = os.path.dirname(os.path.abspath(__file__))


def nota(n):
    """'D4' → Hz (La4 = 440)."""
    nombres = {"C": -9, "C#": -8, "Db": -8, "D": -7, "D#": -6, "Eb": -6, "E": -5, "F": -4, "F#": -3,
               "Gb": -3, "G": -2, "G#": -1, "Ab": -1, "A": 0, "A#": 1, "Bb": 1, "B": 2}
    letra, octava = (n[:-1], int(n[-1]))
    return 440.0 * 2 ** ((nombres[letra] + 12 * (octava - 4)) / 12)


def lienzo(seg):
    return np.zeros((int(seg * SR) + SR, 2))


def poner(lienzo_, mono, t0, gain=1.0, pan=0.0):
    i = int(t0 * SR)
    fin = min(len(lienzo_), i + len(mono))
    m = mono[: fin - i] * gain
    izq = np.cos((pan + 1) * np.pi / 4)
    der = np.sin((pan + 1) * np.pi / 4)
    lienzo_[i:fin, 0] += m * izq
    lienzo_[i:fin, 1] += m * der


def envolvente(n, ataque, decaimiento_t60, release, dur):
    t = np.arange(n) / SR
    env = np.minimum(1.0, t / max(ataque, 1e-4))
    env *= np.exp(-6.9 * t / decaimiento_t60)
    corte = t > dur
    env[corte] *= np.exp(-(t[corte] - dur) / max(release, 1e-3) * 5)
    return env


def piano_electrico(f, dur, vel=1.0):
    n = int((dur + 1.2) * SR)
    t = np.arange(n) / SR
    indice = 1.6 * np.exp(-t * 4.0) + 0.25
    s = np.sin(2 * np.pi * f * t + indice * np.sin(2 * np.pi * f * t))
    s += 0.18 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 3)
    return s * envolvente(n, 0.004, 2.2, 0.25, dur) * vel


def campana(f, dur, vel=1.0):
    n = int((dur + 1.5) * SR)
    t = np.arange(n) / SR
    indice = 2.2 * np.exp(-t * 7) + 0.4
    s = np.sin(2 * np.pi * f * t + indice * np.sin(2 * np.pi * 3.5 * f * t))
    s += 0.25 * np.sin(2 * np.pi * 4.0 * f * t) * np.exp(-t * 9)
    return s * envolvente(n, 0.002, 1.6, 0.4, dur) * vel


def colchon(f, dur, vel=1.0):
    n = int((dur + 1.0) * SR)
    t = np.arange(n) / SR
    s = np.zeros(n)
    for desafine in (-0.004, 0.0, 0.004):
        for k in range(1, 10):
            s += np.sin(2 * np.pi * f * (1 + desafine) * k * t) * (1 / k) * np.exp(-k / 3.5)
    s /= 3
    ataque = np.minimum(1.0, t / 0.7)
    caida = np.ones(n)
    corte = t > dur
    caida[corte] = np.exp(-(t[corte] - dur) / 0.35)
    return s * ataque * caida * vel


def bajo(f, dur, vel=1.0):
    n = int((dur + 0.6) * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t)
    return s * envolvente(n, 0.01, 3.0, 0.2, dur) * vel


def soplo(dur, sube=True):
    n = int(dur * SR)
    ruido = np.random.default_rng(7).standard_normal(n)
    t = np.arange(n) / SR
    # filtro paso banda casero: diferencia de dos medias móviles que se desplazan
    salida = np.zeros(n)
    trozo = 512
    for i in range(0, n, trozo):
        frac = i / n if sube else 1 - i / n
        ancho = int(40 - 34 * frac) or 1
        seg = ruido[i:i + trozo + ancho]
        lento = np.convolve(seg, np.ones(ancho) / ancho, mode="same")[: len(ruido[i:i + trozo])]
        salida[i:i + trozo] = lento
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2
    return salida * env


def acorde(lz, notas, t0, dur, gain, pan_ancho=0.5):
    for k, n_ in enumerate(notas):
        pan = (k / max(1, len(notas) - 1) - 0.5) * pan_ancho
        poner(lz, colchon(nota(n_), dur), t0, gain / len(notas), pan)


def normalizar(lz, pico_db=-3.0):
    pico = np.max(np.abs(lz)) or 1.0
    return lz * (10 ** (pico_db / 20) / pico)


def recortar(lz, seg):
    lz = lz[: int(seg * SR)]
    fade = int(0.08 * SR)
    lz[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return lz


def guardar(lz, nombre):
    wav = os.path.join(AQUI, nombre + ".wav")
    mp3 = os.path.join(AQUI, nombre + ".mp3")
    datos = (np.clip(lz, -1, 1) * 32767).astype("<i2")
    import wave
    with wave.open(wav, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(datos.tobytes())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-c:a", "libmp3lame", "-b:a", "192k", mp3], check=True)
    os.remove(wav)
    print("ok", mp3)


# ---------------------------------------------------------------- piezas
def intro():
    negra = 60 / 104
    lz = lienzo(8)
    progresion = [  # (bajo, colchón, duración en negras)
        ("D2", ["F#3", "A3", "C#4", "E4"], 2),
        ("B1", ["D3", "F#3", "A3", "E4"], 2),
        ("G1", ["B2", "F#3", "A3", "D4"], 2),
        ("A1", ["D3", "G3", "B3", "E4"], 2),
        ("D2", ["F#3", "A3", "B3", "E4"], 6),
    ]
    t = 0.0
    for b, notas_, negras in progresion:
        d = negras * negra
        poner(lz, bajo(nota(b), d), t, 0.55)
        acorde(lz, notas_, t, d, 0.55)
        # piano eléctrico: arpegio suave en corcheas sobre las notas del acorde
        for k in range(int(negras * 2) if negras <= 2 else 4):
            n_ = notas_[k % len(notas_)]
            poner(lz, piano_electrico(nota(n_) * 2, negra / 2, 0.8), t + k * negra / 2, 0.16, -0.3 + 0.2 * (k % 3))
        t += d
    melodia = [("F#5", 0, 1), ("A5", 1, 0.5), ("D6", 1.5, 0.5), ("C#6", 2, 1.5), ("B5", 3.5, 0.5),
               ("D6", 4, 0.5), ("C#6", 4.5, 0.5), ("B5", 5, 1), ("A5", 6, 2), ("D6", 8, 4)]
    for n_, en, dur in melodia:
        poner(lz, campana(nota(n_), dur * negra, 0.9), en * negra, 0.22, 0.2)
    # pulso muy discreto en los cuatro primeros compases
    for k in range(16):
        poner(lz, soplo(0.05), k * negra / 2, 0.035 if k % 2 else 0.05, 0.4)
    return recortar(normalizar(lz), 7.6)


def transicion():
    lz = lienzo(2.2)
    poner(lz, soplo(0.55, sube=True), 0.0, 0.18)
    poner(lz, campana(nota("A5"), 0.6, 0.9), 0.5, 0.25, -0.2)
    poner(lz, campana(nota("D6"), 0.6, 0.9), 0.62, 0.25, 0.2)
    poner(lz, bajo(nota("D2"), 0.5), 0.5, 0.35)
    acorde(lz, ["F#3", "A3", "D4"], 0.5, 0.6, 0.25)
    return recortar(normalizar(lz, -4), 2.0)


def fondo():
    negra = 60 / 76
    lz = lienzo(27)
    progresion = [("D2", ["F#3", "A3", "C#4", "E4"]), ("G1", ["B2", "D3", "F#3", "A3"]),
                  ("B1", ["D3", "F#3", "A3", "C#4"]), ("A1", ["C#3", "E3", "F#3", "B3"])]
    t = 0.0
    for vuelta in range(2):
        for b, notas_ in progresion:
            d = 4 * negra
            poner(lz, bajo(nota(b), d), t, 0.35)
            acorde(lz, notas_, t, d, 0.5, 0.8)
            for k, n_ in enumerate([notas_[1], notas_[3]]):
                poner(lz, piano_electrico(nota(n_) * 2, negra, 0.6), t + k * 2 * negra, 0.08, 0.3 - 0.6 * k)
            t += d
    lz = normalizar(lz, -6)
    total = int(t * SR)
    lz = lz[:total + int(0.6 * SR)]
    # bucle sin saltos: la cola se funde con el principio
    solape = int(0.6 * SR)
    lz[:solape] += lz[total:total + solape] * np.linspace(1, 0, solape)[:, None]
    return lz[:total]


def cierre():
    negra = 60 / 96
    lz = lienzo(8)
    progresion = [("G1", ["B2", "F#3", "A3", "D4"], 2), ("A1", ["D3", "G3", "B3", "E4"], 2),
                  ("D2", ["F#3", "A3", "C#4", "E4"], 6)]
    t = 0.0
    for b, notas_, negras in progresion:
        d = negras * negra
        poner(lz, bajo(nota(b), d), t, 0.5)
        acorde(lz, notas_, t, d, 0.55)
        t += d
    for n_, en, dur in [("D6", 0, 1), ("B5", 1, 1), ("A5", 2, 1), ("F#5", 3, 1), ("A5", 4, 3)]:
        poner(lz, campana(nota(n_), dur * negra, 0.9), en * negra, 0.22, 0.15)
    return recortar(normalizar(lz), 6.5)


if __name__ == "__main__":
    for nombre, f in (("intro", intro), ("transicion", transicion), ("fondo", fondo), ("cierre", cierre)):
        guardar(f(), nombre)
