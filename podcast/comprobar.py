"""Escucha el último episodio (transcripción automática) y lo compara con el guion.
Deja el informe en Dropbox («Comprobación.txt»); en GitHub solo salen cifras."""
import difflib
import json
import os
import re
import subprocess
import tempfile
import unicodedata

from . import config, dropbox


def nota(titulo, texto):
    texto = texto.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::notice title={titulo}::{texto[:20000]}", flush=True)


def norma(t):
    t = "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9ñ]+", t)


def main():
    token = dropbox.token_acceso()
    mp3 = dropbox.descargar(token, config.DROPBOX_MP3)
    md = dropbox.descargar(token, config.DROPBOX_GUION).decode("utf-8", "replace")
    with tempfile.TemporaryDirectory() as tmp:
        ruta = os.path.join(tmp, "e.mp3")
        open(ruta, "wb").write(mp3)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta],
                                   capture_output=True, text=True).stdout or 0)
        sil = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", ruta, "-af", "silencedetect=noise=-45dB:d=2",
                              "-f", "null", "-"], capture_output=True, text=True).stderr
        silencios = [(float(a), float(b)) for a, b in re.findall(r"silence_start: ([\d.]+).*?silence_duration: ([\d.]+)", sil, re.S)]
        lu = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", ruta, "-af", "ebur128", "-f", "null", "-"],
                            capture_output=True, text=True).stderr
        integrada = re.findall(r"I:\s+(-?[\d.]+) LUFS", lu)
        from faster_whisper import WhisperModel
        modelo = WhisperModel(os.environ.get("WHISPER", "base"), device="cpu", compute_type="int8")
        trozos, _ = modelo.transcribe(ruta, language="es", vad_filter=True, beam_size=1)
        trozos = list(trozos)
    texto_oido = " ".join(t.text.strip() for t in trozos)
    guion = " ".join(re.sub(r"^\*\*[^*]+:\*\*\s*", "", l) for l in md.splitlines() if l.startswith("**"))
    a, b = norma(guion), norma(texto_oido)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    parecido = sm.ratio()
    faltan = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("delete", "replace") and i2 - i1 >= 8:
            faltan.append(" ".join(a[i1:i2])[:200])
    sospechas = [p for p in ("lucia:", "martin:", "charla desenfadada", "lee esta conversacion", "speech", "style")
                 if p in " ".join(b) or p in texto_oido.lower()]
    ppm = len(b) / max(dur / 60, 0.1)
    informe = [f"Duración: {dur / 60:.1f} min · sonoridad: {integrada[-1] if integrada else '?'} LUFS",
               f"Palabras guion: {len(a)} · oídas: {len(b)} · parecido guion/audio: {parecido:.0%} · {ppm:.0f} palabras por minuto",
               f"Silencios de más de 2 s: {[(round(s), round(d, 1)) for s, d in silencios] or 'ninguno'}",
               f"Posibles lecturas raras: {sospechas or 'ninguna'}",
               "", "Trozos del guion que no se oyen (o se oyen distinto):"] + [f"  - {f}" for f in faltan[:25]] + \
              ["", "Transcripción con tiempos:"] + [f"[{int(t.start // 60):02d}:{int(t.start % 60):02d}] {t.text.strip()}" for t in trozos]
    dropbox.subir(token, "/Comprobación.txt", "\n".join(informe).encode("utf-8"))
    nota("Comprobación", f"{dur / 60:.1f} min · parecido {parecido:.0%} · {ppm:.0f} p/min · silencios>2s: {len(silencios)} · "
                         f"lecturas raras: {len(sospechas)} · trozos que no se oyen: {len(faltan)}")


if __name__ == "__main__":
    main()
