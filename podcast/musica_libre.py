"""Sintonía de biblioteca libre (Mixkit: uso gratuito en proyectos propios, sin atribución).

    python -m podcast.musica_libre listar           → anotaciones con títulos y enlaces de pistas
    python -m podcast.musica_libre preparar URL     → recorta entrada y cierre y los deja en Dropbox /musica

La música NO se guarda en este repositorio público (la licencia no permite redistribuir las
pistas sueltas): vive solo en la carpeta privada del pódcast en Dropbox.
"""
import html as htmlmod
import io
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
PAGINAS = ["https://mixkit.co/free-stock-music/tag/intro/",
           "https://mixkit.co/free-stock-music/mood/happy/",
           "https://mixkit.co/free-stock-music/tag/podcast/"]


def nota(titulo, texto):
    texto = texto.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::notice title={titulo}::{texto[:20000]}", flush=True)


def bajar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def listar():
    for pag in PAGINAS:
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
            filas.append(f"{nombre} | {u}")
        nota(f"Mixkit {pag.split('/')[-2]} ({len(filas)})", "\n".join(filas) or html[:1500])


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
        # entrada: los primeros segundos con música, bajando al final para que entren las voces
        _ffmpeg("-ss", f"{t0:.2f}", "-t", f"{intro_seg}", "-i", orig, "-af",
                f"afade=t=in:d=0.3,afade=t=out:st={intro_seg - 3.5}:d=3.5", "-ac", "2", "-b:a", "192k", intro)
        # cierre: el final natural de la pista
        st = max(0.0, dur - cierre_seg)
        _ffmpeg("-ss", f"{st:.2f}", "-i", orig, "-af", "afade=t=in:d=1.2", "-ac", "2", "-b:a", "192k", cierre)
        for nombre, ruta in (("intro.mp3", intro), ("cierre.mp3", cierre)):
            with open(ruta, "rb") as f:
                dropbox.subir(token, f"/musica/{nombre}", f.read())
        nota("Música preparada", f"pista de {dur:.0f}s (empieza a sonar en {t0:.1f}s) · entrada {intro_seg:.0f}s y "
                                 f"cierre {cierre_seg:.0f}s subidos a Dropbox /musica · origen {url}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "preparar":
        preparar(sys.argv[2])
    else:
        listar()
