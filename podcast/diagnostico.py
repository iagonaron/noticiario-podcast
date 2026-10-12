"""Diagnóstico técnico (sin datos personales). Resultados como anotaciones de GitHub («::notice::»).

    python -m podcast.diagnostico elpais     → qué ve el robot de El País Exprés
    python -m podcast.diagnostico noticias   → abre el noticiario y cuenta lo que trae
    python -m podcast.diagnostico voz        → prueba corta de la voz de Gemini (una y dos voces) y de Edge
    python -m podcast.diagnostico guion      → pide un guion de prueba a Gemini con noticias inventadas
"""
import json
import re
import sys
import time
import traceback
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


def nota(titulo, texto, nivel="notice"):
    texto = str(texto).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::{nivel} title={titulo}::{texto[:20000]}", flush=True)


def elpais():
    for nombre, url in [("directo", "https://elpais.com/expres/"),
                        ("netlify", "https://noticiarioiago.netlify.app/proxy/elpais.com/expres/")]:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                html = r.read().decode("utf-8", "replace")
                nota(f"El País {nombre}", f"HTTP {r.status} · {len(html)} bytes · articles={html.lower().count('<article')}")
        except Exception as e:
            nota(f"El País {nombre}", repr(e)[:300])


def noticias():
    from . import noticias as nt
    t0 = time.time()
    d = nt.recoger()
    nota("Noticiario", f"{time.time() - t0:.0f}s · carga={d.get('carga')} · portada {len(d['portada'])} · "
                       f"interés {len(d['interes'])} · local {len(d['local'])} · alertas {len(d['alertas_sanitarias'])} · "
                       f"madrid={d.get('madrid')}")
    fallos = [l for l in d.get("diagnostico") or [] if "fail" in l or "retry" in l]
    nota("Fuentes con fallos", "\n".join(fallos) or "ninguna")


def voz():
    from . import voces, config
    tanda2 = {"bloque": "portada", "turnos": [
        {"voz": "A", "texto": "Oye, ¿te has enterado de lo del tranvía en Coruña? Parece que vuelve, aunque sea de prueba."},
        {"voz": "B", "texto": "¡No me digas! Pues ya era hora. A ver si esta vez dura más de dos semanas, ¿eh?"},
        {"voz": "A", "texto": "Eso dicen. Y ojo, que el billete sería gratis el primer mes."}]}
    tanda1 = {"bloque": "rapido", "turnos": [{"voz": "B", "texto": "En la agenda de hoy: a las diez y media de la mañana, dentista. Y mañana, nada."}]}
    for via, modelo in config.MODELOS_VOZ:
        for nombre, tanda in (("dos voces", tanda2), ("una voz", tanda1)):
            t0 = time.time()
            try:
                wav = voces._llamada(via, modelo, tanda)
                ok, seg, esp = voces._razonable(wav, tanda)
                nota(f"Voz {modelo} {via} · {nombre}", f"OK en {time.time() - t0:.1f}s · audio {seg:.1f}s (esperado ~{esp:.1f}s) · razonable={ok}")
            except Exception as e:
                nota(f"Voz {modelo} {via} · {nombre}", f"FALLO en {time.time() - t0:.1f}s · {str(e)[:600]}", "warning")
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            auds, motor = voces.sintetizar_edge([tanda2], tmp)
            nota("Voz Edge", f"OK · {voces.duracion_wav(auds[0]):.1f}s · {motor}")
    except Exception as e:
        nota("Voz Edge", f"FALLO · {str(e)[:500]}", "warning")


def guion():
    from . import guion as g, util
    falsas = {"portada": [{"titulo": f"Noticia de prueba {i}", "fuente": "Prueba", "categoria": "",
                           "texto": "Texto de prueba con algo de contexto sobre un asunto público inventado. " * 6}
                          for i in range(6)],
              "interes": [], "local": [], "alertas_sanitarias": [], "madrid": {"jugo": False}}
    t0 = time.time()
    segs, info = g.escribir(util.ahora(), falsas)
    nota("Guion de prueba", f"{time.time() - t0:.0f}s · modelo {info.get('modelo')} · {info.get('palabras')} palabras · "
                            f"{len(segs)} turnos · avisos: {info.get('avisos')}"[:3000])


if __name__ == "__main__":
    for prueba in (sys.argv[1:] or ["elpais"]):
        try:
            {"elpais": elpais, "noticias": noticias, "voz": voz, "guion": guion}[prueba]()
        except Exception as e:
            nota(f"Diagnóstico {prueba}", traceback.format_exc()[-1500:], "warning")
