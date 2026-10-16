"""Música de biblioteca libre (Mixkit: uso gratuito en proyectos propios, sin atribución).

    python -m podcast.musica_libre listar [PÁGINA…]   → anotaciones con títulos y enlaces de pistas
    python -m podcast.musica_libre analizar URL…      → duración, tempo, sonoridad y lo estable que es cada pista
    python -m podcast.musica_libre fondo URL          → guarda la pista entera como cama musical (Dropbox /musica/fondo.mp3)
    python -m podcast.musica_libre preparar URL       → (antiguo) recorta entrada y cierre en Dropbox /musica

La música NO se guarda en este repositorio público (la licencia no permite redistribuir las
pistas sueltas): vive solo en la carpeta privada del pódcast en Dropbox.
"""
import html as htmlmod
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
PAGINAS = ["https://mixkit.co/free-stock-music/tag/news/",
           "https://mixkit.co/free-stock-music/tag/corporate/",
           "https://mixkit.co/free-stock-music/tag/technology/",
           "https://mixkit.co/free-stock-music/tag/business/"]


def nota(titulo, texto):
    texto = texto.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::notice title={titulo}::{texto[:20000]}", flush=True)


def bajar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def listar(paginas=None):
    for pag in (paginas or PAGINAS):
        try:
            html = bajar(pag).decode("utf-8", "replace")
        except Exception as e:
            nota(f"Mixkit {pag}", f"no se pudo leer: {e}")
            continue
        mp3 = re.findall(r"https://assets\.mixkit\.co/[^\"'\s<>]+?\.mp3", html)
        filas = []
        for u in dict.fromkeys(mp3):
            i = html.find(u)
            trozo = html[max(0, i - 4000):i]
            titulos = re.findall(r"(?:title|aria-label|data-title)=\"([^\"]{3,80})\"", trozo)
            h = re.findall(r"<h\d[^>]*>\s*(?:<a[^>]*>)?\s*([^<]{3,80})<", trozo)
            nombre = htmlmod.unescape((h[-1] if h else (titulos[-1] if titulos else "?")).strip())
            dur = re.findall(r"\b(\d{1,2}:\d{2})\b", html[i:i + 3000])
            filas.append(f"{nombre} | {dur[0] if dur else '?'} | {u}")
        nota(f"Mixkit {pag.rstrip('/').split('/')[-1]} ({len(filas)})", "\n".join(filas) or html[:1500])


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def _inicio_sonoro(ruta):
    """Segundo en el que la música empieza de verdad (evita silencios iniciales)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", ruta, "-af",
                        "silencedetect=noise=-40dB:d=0.3", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"silence_start: 0(?:\.0+)?\b.*?silence_end: ([\d.]+)", r.stderr, re.S)
    return float(m.group(1)) if m else 0.0


def _duracion(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def _caracteristicas(ruta):
    """Duración, sonoridad integrada, rango de sonoridad (LRA: cuanto más bajo, más estable), tempo
    aproximado y brillo (centroide espectral), para elegir una cama musical sin oírla."""
    import numpy as np
    dur = _duracion(ruta)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", ruta, "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    integ = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    lra = re.findall(r"LRA:\s+([\d.]+) LU", r.stderr)
    pcm = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", ruta, "-ac", "1", "-ar", "22050",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
    hop, win = 512, 2048
    n = max(1, (len(x) - win) // hop)
    frames = np.lib.stride_tricks.as_strided(x, shape=(n, win), strides=(x.strides[0] * hop, x.strides[0]))
    espec = np.abs(np.fft.rfft(frames * np.hanning(win), axis=1))
    flujo = np.maximum(0, np.diff(espec, axis=0)).sum(axis=1)
    flujo = (flujo - flujo.mean()) / (flujo.std() + 1e-9)
    ac = np.correlate(flujo, flujo, mode="full")[len(flujo) - 1:]
    fps = 22050 / hop
    lags = np.arange(len(ac))
    validos = (lags >= fps * 60 / 180) & (lags <= fps * 60 / 60)
    bpm = 60 * fps / lags[validos][np.argmax(ac[validos])] if validos.any() else 0
    freqs = np.fft.rfftfreq(win, 1 / 22050)
    centroide = float((espec * freqs).sum() / (espec.sum() + 1e-9))
    # estabilidad: desviación de la energía en ventanas de 3 s (dB)
    v = int(22050 * 3)
    energias = [20 * np.log10(np.sqrt(np.mean(x[i:i + v] ** 2)) + 1e-9) for i in range(0, max(1, len(x) - v), v)]
    return {"dur": dur, "lufs": float(integ[-1]) if integ else None, "lra": float(lra[-1]) if lra else None,
            "bpm": round(float(bpm)), "centroide_hz": round(centroide), "desv_db": round(float(np.std(energias)), 1)}


def analizar(urls):
    filas = []
    with tempfile.TemporaryDirectory() as tmp:
        for k, url in enumerate(urls):
            ruta = os.path.join(tmp, f"p{k}.mp3")
            try:
                with open(ruta, "wb") as f:
                    f.write(bajar(url))
                c = _caracteristicas(ruta)
                t = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=title,artist,genre",
                                    "-of", "default=nw=1:nk=1", ruta], capture_output=True, text=True).stdout
                titulo = " / ".join(x.strip() for x in t.splitlines() if x.strip())[:80] or "?"
                filas.append(f"{url.split('/')[-1]} «{titulo}» · {c['dur']:.0f}s · {c['bpm']} bpm · {c['lufs']} LUFS · "
                             f"LRA {c['lra']} · desv {c['desv_db']} dB · brillo {c['centroide_hz']} Hz")
            except Exception as e:
                filas.append(f"{url} · error {e}")
    nota("Análisis de pistas", "\n".join(filas))


def describir(urls):
    """Le pide a Gemini que «escuche» cada pista y diga si sirve de cama de telediario."""
    import base64
    import json
    clave = os.environ.get("GEMINI_API_KEY", "")
    modelos = (os.environ.get("MODELOS_OIDO") or "gemini-3.6-flash,gemini-3-flash-preview,gemini-3.8-flash").split(",")
    pregunta = ("Escucha esta pista musical entera. Responde en español y en una sola línea: género, TODOS los "
                "instrumentos que se oyen (di expresamente si hay vientos metales —trompeta, trompa, trombón, sección "
                "de metales sintética— y si hay guitarra), si la batería o la percusión llevan un ritmo marcado, "
                "ambiente y tempo aproximado. Y si serviría como música de fondo continua bajo las voces de un "
                "informativo de radio moderno, con batería y ritmo pero sin vientos metales (nota del 1 al 10, y por "
                "qué). Empieza por la nota, así: «8/10 · …».")
    filas = []
    for url in urls:
        audio = bajar(url)
        cuerpo = {"contents": [{"parts": [{"inline_data": {"mime_type": "audio/mpeg",
                                                         "data": base64.b64encode(audio).decode()}},
                                          {"text": pregunta}]}]}
        texto = "?"
        for m in modelos:
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{m.strip()}:generateContent",
                data=json.dumps(cuerpo).encode(), headers={"x-goog-api-key": clave, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    j = json.loads(r.read())
                partes = j["candidates"][0]["content"]["parts"]
                texto = " ".join(p.get("text", "") for p in partes if not p.get("thought")).strip().replace("\n", " ")
                break
            except Exception as e:
                texto = f"error con {m}: {e}"
        filas.append(f"{url.split('/')[-1]} → {texto[:400]}")
    nota("Pistas escuchadas por Gemini", "\n".join(filas))


def _voz_de_muestra(token):
    """Unos turnos de los titulares del último episodio (del crudo guardado en Dropbox), como piezas
    para el montaje: así cada muestra suena como sonaría el programa."""
    import json
    from . import alinear, dropbox
    carpeta = "/Pruebas/Crudo del episodio"
    meta = json.loads(dropbox.descargar(token, f"{carpeta}/lotes.json").decode("utf-8"))
    turnos = meta["turnos"]
    elegidos = [i for i, t in enumerate(turnos) if t["bloque"] == "titulares" and t.get("noticia") in (1, 2)][:9]
    piezas = {}
    for lote in meta["lotes"]:
        if lote.get("leyo_etiqueta") or not set(lote["indices"]) & set(elegidos):
            continue
        mp3 = dropbox.descargar(token, f"{carpeta}/{lote['fichero']}")
        wav = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", "24000",
                              "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"], input=mp3, capture_output=True, check=True).stdout
        for idx, (a, b) in zip(lote["indices"], lote["tramos"]):
            if idx in elegidos:
                piezas[idx] = alinear.recortar(wav, a, b)
    return [{"wav": piezas[i], "bloque": turnos[i]["bloque"], "noticia": turnos[i].get("noticia"),
             "voz": turnos[i]["voz"]} for i in elegidos if i in piezas]


def muestras(urls):
    """Para cada pista candidata, un trozo de programa de verdad (los primeros titulares del último
    episodio con esa música de fondo) en Dropbox /Pruebas/Músicas para elegir/, para elegir de oído."""
    from pydub import AudioSegment
    from . import dropbox, montaje
    token = dropbox.token_acceso()
    piezas = _voz_de_muestra(token)
    filas = []
    with tempfile.TemporaryDirectory() as tmp:
        for k, url in enumerate(urls, 1):
            try:
                orig = os.path.join(tmp, f"p{k}.mp3")
                with open(orig, "wb") as f:
                    f.write(bajar(url))
                t0 = _inicio_sonoro(orig)
                limpia = os.path.join(tmp, f"l{k}.mp3")
                _ffmpeg("-ss", f"{t0:.2f}", "-i", orig, "-ac", "2", "-b:a", "192k", limpia)
                musica = montaje.cargar_musica({"fondo": open(limpia, "rb").read()})
                wav, mp3 = os.path.join(tmp, f"m{k}.wav"), os.path.join(tmp, f"m{k}.mp3")
                dur = montaje.montar(piezas, musica, wav)
                montaje.a_mp3(wav, mp3, {"title": f"Muestra {k}"})
                nombre = re.sub(r"[^\w\- ]", "", url.rstrip("/").split("/")[-1].replace(".mp3", ""))
                dropbox.subir(token, f"/Pruebas/Músicas para elegir/{k} pista {nombre}.mp3", open(mp3, "rb").read())
                filas.append(f"{k} · {url} · {dur:.0f}s")
            except Exception as e:
                filas.append(f"{k} · {url} · error {e}")
    nota("Muestras de música", "\n".join(filas))


def _leer(ruta, sr=44100):
    """Audio estéreo en float32 (2, n) a 44,1 kHz."""
    import numpy as np
    pcm = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", ruta, "-ac", "2", "-ar", str(sr),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(pcm, np.float32).reshape(-1, 2).T.copy()


def _escribir(x, ruta, sr=44100):
    import numpy as np
    pico = float(np.max(np.abs(x))) or 1.0
    x = x * (0.97 / pico if pico > 0.97 else 1.0)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(sr), "-ac", "2",
                    "-i", "-", ruta], input=x.T.astype(np.float32).tobytes(), check=True)


def _separar(ruta):
    """Demucs (htdemucs): {'drums', 'bass', 'other', 'vocals'} → (2, n) float32 a 44,1 kHz."""
    import numpy as np
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    modelo = get_model("htdemucs")
    modelo.eval()
    x = torch.from_numpy(_leer(ruta, modelo.samplerate))
    ref = x.mean(0)
    media, desv = ref.mean(), ref.std() + 1e-8
    with torch.no_grad():
        fuentes = apply_model(modelo, ((x - media) / desv)[None], device="cpu", split=True, overlap=0.25,
                              progress=False)[0]
    fuentes = fuentes * desv + media
    return {n: fuentes[i].numpy().astype(np.float32) for i, n in enumerate(modelo.sources)}


def _filtro(x, args, tmp, nombre):
    """Pasa audio (2, n) por un filtro de ffmpeg y lo devuelve igual de largo."""
    import numpy as np
    ent, sal = os.path.join(tmp, f"{nombre}-e.wav"), os.path.join(tmp, f"{nombre}-s.wav")
    _escribir(x, ent)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", ent, "-af", args, sal], check=True)
    y = _leer(sal)
    n = x.shape[1]
    return y[:, :n] if y.shape[1] >= n else np.pad(y, ((0, 0), (0, n - y.shape[1])))


def _subir_tono(x, semitonos, tmp, nombre):
    """Más aguda sin cambiar el tempo (rubberband si ffmpeg lo trae; si no, asetrate+atempo)."""
    r = 2 ** (semitonos / 12)
    try:
        return _filtro(x, f"rubberband=pitch={r:.6f}:pitchq=quality:transients=crisp", tmp, nombre)
    except subprocess.CalledProcessError:
        return _filtro(x, f"asetrate={44100 * r:.0f},aresample=44100,atempo={1 / r:.6f}", tmp, nombre)


def _inicio_del_ritmo(bateria, sr=44100):
    """Segundo en el que la batería ya suena con fuerza (para que la cama empiece con ritmo)."""
    import numpy as np
    mono = bateria.mean(0)
    v = int(sr * 0.5)
    energia = np.array([np.sqrt(np.mean(mono[i:i + v] ** 2)) for i in range(0, len(mono) - v, v)])
    if len(energia) < 12:
        return 0.0
    suave = np.convolve(energia, np.ones(8) / 8, mode="valid")
    umbral = 0.6 * np.median(suave)
    for k, e in enumerate(suave):
        if e >= umbral:
            return k * 0.5 + 1.0
    return 0.0


def afinar(url, variantes=("2", "3/4", "4")):
    """Versiones de una pista para la cama musical: sin caja (se separa la batería con Demucs y se deja
    solo el bombo y los platos), más aguda (+semitonos, el tempo igual o un poco más rápido: «3/4» es
    +3 semitonos y un 4 % más rápida) y empezando donde ya suena el ritmo. Cada versión va a Dropbox
    /Pruebas/Pistas afinadas/ y, como trozo de programa real, a /Pruebas/Músicas para elegir/."""
    import numpy as np
    from . import dropbox, montaje
    token = dropbox.token_acceso()
    piezas = _voz_de_muestra(token)
    filas = []
    nombre_pista = url.rstrip("/").split("/")[-1].replace(".mp3", "")
    with tempfile.TemporaryDirectory() as tmp:
        orig = os.path.join(tmp, "orig.mp3")
        with open(orig, "wb") as f:
            f.write(bajar(url))
        partes = _separar(orig)
        tonal = partes["bass"] + partes["other"] + partes["vocals"]
        # sin caja: del canal de batería solo queda el bombo (graves) y los platos (agudos)
        bateria = _filtro(partes["drums"],
                          "asplit[a][b];[a]lowpass=f=115,lowpass=f=115[g];[b]highpass=f=9000,highpass=f=9000[p];"
                          "[g][p]amix=inputs=2:normalize=0", tmp, "bateria")
        bateria *= 1.25
        t0 = _inicio_del_ritmo(partes["drums"])
        for k, var in enumerate(variantes, 1):
            semitonos, _, tempo = var.partition("/")
            semitonos, tempo = float(semitonos or 0), float(tempo or 0)
            mezcla = _subir_tono(tonal, semitonos, tmp, f"tono{k}") + bateria
            if tempo:
                mezcla = _filtro(mezcla, f"atempo={1 + tempo / 100:.4f}", tmp, f"tempo{k}")
                inicio = t0 / (1 + tempo / 100)
            else:
                inicio = t0
            mezcla = mezcla[:, int(inicio * 44100):]
            fundido = np.linspace(0, 1, 441)
            mezcla[:, :441] *= fundido
            etiqueta = f"{nombre_pista} {'+' if semitonos >= 0 else ''}{semitonos:g} semitonos" + (f" {tempo:+g} %" if tempo else "")
            pista = os.path.join(tmp, f"pista{k}.mp3")
            wav = os.path.join(tmp, f"pista{k}.wav")
            _escribir(mezcla, wav)
            _ffmpeg("-i", wav, "-b:a", "192k", pista)
            dropbox.subir(token, f"/Pruebas/Pistas afinadas/{etiqueta}.mp3", open(pista, "rb").read())
            musica = montaje.cargar_musica({"fondo": open(pista, "rb").read()})
            prog_wav, prog_mp3 = os.path.join(tmp, f"m{k}.wav"), os.path.join(tmp, f"m{k}.mp3")
            dur = montaje.montar(piezas, musica, prog_wav)
            montaje.a_mp3(prog_wav, prog_mp3, {"title": etiqueta})
            dropbox.subir(token, f"/Pruebas/Músicas para elegir/2{chr(96 + k)} {etiqueta}.mp3", open(prog_mp3, "rb").read())
            filas.append(f"2{chr(96 + k)} · {etiqueta} · empieza en {inicio:.1f}s · muestra de {dur:.0f}s")
    nota("Pistas afinadas", "\n".join(filas))


def usar(ruta):
    """Pone como cama musical un fichero que ya está en Dropbox (p. ej. una pista afinada), guardando
    antes una copia de la cama de ahora."""
    import datetime as dt
    from . import dropbox
    token = dropbox.token_acceso()
    actual = dropbox.descargar(token, "/musica/fondo.mp3")
    if actual:
        dropbox.subir(token, f"/musica/fondo - copia {dt.datetime.now():%Y-%m-%d %H%M}.mp3", actual)
    nueva = dropbox.descargar(token, ruta)
    if not nueva:
        raise SystemExit(f"no encuentro {ruta}")
    dropbox.subir(token, "/musica/fondo.mp3", nueva)
    nota("Cama musical cambiada", f"ahora: {ruta} · copia de la anterior en /musica")


def fondo(url):
    """Guarda la pista entera (sin el silencio inicial) como cama musical del programa."""
    from . import dropbox
    token = dropbox.token_acceso()
    with tempfile.TemporaryDirectory() as tmp:
        orig = os.path.join(tmp, "pista.mp3")
        with open(orig, "wb") as f:
            f.write(bajar(url))
        t0 = _inicio_sonoro(orig)
        sal = os.path.join(tmp, "fondo.mp3")
        _ffmpeg("-ss", f"{t0:.2f}", "-i", orig, "-ac", "2", "-b:a", "192k", sal)
        with open(sal, "rb") as f:
            dropbox.subir(token, "/musica/fondo.mp3", f.read())
        c = _caracteristicas(sal)
        nota("Cama musical guardada", f"{c} · origen {url}")


def preparar(url, intro_seg=11.0, cierre_seg=9.0):
    from . import dropbox
    token = dropbox.token_acceso()
    with tempfile.TemporaryDirectory() as tmp:
        orig = os.path.join(tmp, "pista.mp3")
        with open(orig, "wb") as f:
            f.write(bajar(url))
        dur = _duracion(orig)
        t0 = _inicio_sonoro(orig)
        intro = os.path.join(tmp, "intro.mp3")
        cierre = os.path.join(tmp, "cierre.mp3")
        _ffmpeg("-ss", f"{t0:.2f}", "-t", f"{intro_seg}", "-i", orig, "-af",
                f"afade=t=in:d=0.3,afade=t=out:st={intro_seg - 3.5}:d=3.5", "-ac", "2", "-b:a", "192k", intro)
        st = max(0.0, dur - cierre_seg)
        _ffmpeg("-ss", f"{st:.2f}", "-i", orig, "-af", "afade=t=in:d=1.2", "-ac", "2", "-b:a", "192k", cierre)
        for nombre, ruta in (("intro.mp3", intro), ("cierre.mp3", cierre)):
            with open(ruta, "rb") as f:
                dropbox.subir(token, f"/musica/{nombre}", f.read())
        nota("Música preparada", f"pista de {dur:.0f}s · entrada {intro_seg:.0f}s y cierre {cierre_seg:.0f}s · origen {url}")


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "listar"
    resto = [a for a in sys.argv[2:] if a.strip()]
    if modo == "analizar":
        analizar(resto)
    elif modo == "describir":
        describir(resto)
    elif modo == "fondo":
        fondo(resto[0])
    elif modo == "muestras":
        muestras(resto)
    elif modo == "afinar":
        afinar(resto[0], tuple(resto[1:]) or ("2", "3/4", "4"))
    elif modo == "usar":
        usar(" ".join(resto))
    elif modo == "preparar":
        preparar(resto[0])
    else:
        listar(resto or None)
