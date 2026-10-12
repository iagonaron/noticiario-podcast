"""Diagnóstico técnico (sin datos personales). Resultados como anotaciones de GitHub («::notice::»).

    python -m podcast.diagnostico elpais     → qué ve el robot de El País Exprés
    python -m podcast.diagnostico noticias   → abre el noticiario y cuenta lo que trae
    python -m podcast.diagnostico voz        → prueba corta de la voz de Gemini (una y dos voces), Edge y Piper
    python -m podcast.diagnostico edge|piper → solo una de las voces de reserva (no gastan cupo de Gemini)
    python -m podcast.diagnostico vozlarga   → una tanda larga, como las del episodio (1 petición si va bien)
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
                       f"madrid={d.get('madrid')} · claves={d.get('madrid_claves')} · fecha de={d.get('madrid_fecha_clave')}")
    fallos = [l for l in d.get("diagnostico") or [] if "fail" in l or "retry" in l]
    nota("Fuentes con fallos", "\n".join(fallos) or "ninguna")


TANDA2 = {"bloque": "portada", "turnos": [
    {"voz": "A", "texto": "Oye, ¿te has enterado de lo del tranvía en Coruña? Parece que vuelve, aunque sea de prueba."},
    {"voz": "B", "texto": "¡No me digas! Pues ya era hora. A ver si esta vez dura más de dos semanas, ¿eh?"},
    {"voz": "A", "texto": "Eso dicen. Y ojo, que el billete sería gratis el primer mes."}]}
TANDA1 = {"bloque": "rapido", "turnos": [{"voz": "B", "texto": "En la agenda de hoy: a las diez y media de la mañana, dentista. Y mañana, nada."}]}


def voz():
    from . import voces, config
    for via, modelo in config.MODELOS_VOZ:
        for nombre, tanda in (("dos voces", TANDA2), ("una voz", TANDA1)):
            t0 = time.time()
            try:
                wav = voces._llamada(via, modelo, tanda)
                ok, seg, esp = voces._razonable(wav, tanda)
                nota(f"Voz {modelo} {via} · {nombre}", f"OK en {time.time() - t0:.1f}s · audio {seg:.1f}s (esperado ~{esp:.1f}s) · razonable={ok}")
            except Exception as e:
                nota(f"Voz {modelo} {via} · {nombre}", f"FALLO en {time.time() - t0:.1f}s · {str(e)[:600]}", "warning")
    edge()
    piper()


def edge():
    import tempfile
    from . import voces
    t0 = time.time()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            auds = voces.sintetizar_edge([TANDA2], tmp)
            nota("Voz Edge", f"OK en {time.time() - t0:.0f}s · audio {voces.duracion_wav(auds[0]):.1f}s")
    except Exception as e:
        nota("Voz Edge", f"FALLO en {time.time() - t0:.0f}s · {str(e)[:500]}", "warning")


def piper():
    from . import voces
    t0 = time.time()
    try:
        auds = voces.sintetizar_piper([TANDA2, TANDA1])
        nota("Voz Piper", f"OK en {time.time() - t0:.0f}s · audios {[round(voces.duracion_wav(a), 1) for a in auds]} s · "
                          f"registro: {' | '.join(voces.REGISTRO)}")
    except Exception as e:
        nota("Voz Piper", f"FALLO en {time.time() - t0:.0f}s · {traceback.format_exc()[-900:]}", "warning")


def vozlarga():
    """Una tanda larga (como las del episodio) con la cadena de modelos de MODELOS_VOZ: 1 petición si va bien."""
    from . import voces
    turnos = []
    frases_a = ["Bueno, pues vamos con la siguiente, que esta tiene miga.",
                "Resulta que el ayuntamiento quiere peatonalizar otra calle del centro y los comerciantes no lo ven nada claro.",
                "Dicen que si quitan los coches, la gente deja de venir a comprar, aunque los estudios suelen decir justo lo contrario.",
                "Y mientras tanto, los vecinos encantados, porque por fin podrían dormir sin el ruido de las motos."]
    frases_b = ["Ya, es el debate de siempre, ¿no?",
                "A mí me parece que al principio cuesta, pero luego nadie quiere volver atrás.",
                "Pasó en Pontevedra hace años y ahora la ponen de ejemplo en media Europa.",
                "Eso sí, hay que poner aparcamientos fuera y buen transporte, que si no es un lío."]
    i = 0
    while sum(len(t["texto"]) for t in turnos) < 2900:
        turnos.append({"voz": "A", "texto": " ".join(frases_a[(i + k) % 4] for k in range(2)), "bloque": "portada"})
        turnos.append({"voz": "B", "texto": " ".join(frases_b[(i + k) % 4] for k in range(2)), "bloque": "portada"})
        i += 1
    t0 = time.time()
    hechas, pendientes, usados, errores = voces.sintetizar_gemini([{"bloque": "portada", "turnos": turnos}])
    nota("Voz larga", f"{time.time() - t0:.0f}s · hechas {len(hechas)} · pendientes {len(pendientes)} · modelos {usados} · "
                      f"errores {errores} · registro: " + "\n".join(voces.REGISTRO))


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
            {"elpais": elpais, "noticias": noticias, "voz": voz, "guion": guion, "edge": edge,
             "piper": piper, "vozlarga": vozlarga}[prueba]()
        except Exception as e:
            nota(f"Diagnóstico {prueba}", traceback.format_exc()[-1500:], "warning")
