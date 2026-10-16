"""La «huella» de un trozo de voz (tono, brillo y forma del espectro) y la detección de derivas: a veces
Gemini cambia de registro a mitad de un lote (sobre todo en noticias serias) y la voz suena a otro
personaje durante unas cuantas frases. Se detecta comparando cada trozo con la voz de siempre del
mismo episodio, y esas frases se rehacen.
"""
import numpy as np

SR = 16000
UMBRAL_RELATIVO = 2.0     # una frase «rara» se aleja de la voz al menos el doble que la frase típica…
UMBRAL_MINIMO = 2.6       # … y al menos esto (dB de diferencia media en la forma del espectro)
SEGUNDOS_MINIMOS = 2.5    # las frases muy cortas («¡Hasta mañana!») varían mucho: no cuentan


def huella(x, sr=SR):
    """Rasgos de un trozo de voz (16 kHz, mono): tono medio (Hz), variación del tono (semitonos),
    brillo (Hz), forma del espectro en 24 bandas mel (dB, sin el volumen) y segundos con voz."""
    win, hop = 640, 160
    n = (len(x) - win) // hop
    if n < 5:
        return None
    marcos = np.lib.stride_tricks.as_strided(x, shape=(n, win), strides=(x.strides[0] * hop, x.strides[0]))
    marcos = marcos * np.hanning(win)
    energia = 10 * np.log10((marcos ** 2).mean(axis=1) + 1e-10)
    voz = energia > (np.percentile(energia, 95) - 25)
    m = marcos[voz]
    if len(m) < 5:
        return None
    F = np.fft.rfft(m, 2 * win, axis=1)
    ac = np.fft.irfft(np.abs(F) ** 2, axis=1)[:, :win]
    ac = ac / (ac[:, :1] + 1e-12)
    lo, hi = int(sr / 400), int(sr / 70)
    lag = lo + np.argmax(ac[:, lo:hi], axis=1)
    f0 = sr / lag[ac[np.arange(len(m)), lag] > 0.45]
    espec = np.abs(np.fft.rfft(m, axis=1)) ** 2
    freqs = np.fft.rfftfreq(win, 1 / sr)
    brillo = float((espec * freqs).sum() / (espec.sum() + 1e-12))

    def mel(f):
        return 2595 * np.log10(1 + f / 700)

    def imel(z):
        return 700 * (10 ** (z / 2595) - 1)

    bordes = imel(np.linspace(mel(80), mel(7600), 26))
    bandas = np.array([espec[:, (freqs >= bordes[i]) & (freqs < bordes[i + 2])].sum(axis=1).mean()
                       for i in range(24)])
    forma = 10 * np.log10(bandas + 1e-12)
    forma = forma - forma.mean()                      # solo la forma: el volumen no cuenta
    return {"tono": float(np.median(f0)) if len(f0) > 5 else None,
            "var": float(np.std(12 * np.log2(f0 / np.median(f0)))) if len(f0) > 5 else None,
            "brillo": brillo, "forma": forma, "voz_s": len(m) * hop / sr}


def distancias(huellas):
    """Distancia (dB) de cada trozo a la forma típica de la voz (mediana de todos sus trozos)."""
    validas = [h for h in huellas if h]
    if len(validas) < 6:
        return [None] * len(huellas)
    ref = np.median([h["forma"] for h in validas], axis=0)
    return [float(np.sqrt(np.mean((h["forma"] - ref) ** 2))) if h else None for h in huellas]


def derivas(huellas):
    """Tramos de frases seguidas (de la misma voz, en su orden) que suenan distintas a la voz de
    siempre: [(primera, última)] en posiciones de la lista, y las distancias."""
    d = distancias(huellas)
    utiles = [x for x, h in zip(d, huellas) if x is not None and h["voz_s"] >= SEGUNDOS_MINIMOS]
    if len(utiles) < 6:
        return [], d
    tipica = float(np.median(utiles))
    corte = max(UMBRAL_MINIMO, UMBRAL_RELATIVO * tipica)
    raras = [x is not None and h and h["voz_s"] >= SEGUNDOS_MINIMOS and x > corte for x, h in zip(d, huellas)]
    tramos, i = [], 0
    while i < len(raras):
        if raras[i]:
            j = i
            while j + 1 < len(raras) and raras[j + 1]:
                j += 1
            if j > i:                                   # una frase suelta rara no es una deriva
                tramos.append((i, j))
            i = j + 1
        else:
            i += 1
    return tramos, d
