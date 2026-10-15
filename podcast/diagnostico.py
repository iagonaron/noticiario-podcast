"""Diagnóstico técnico (sin datos personales). Resultados como anotaciones de GitHub («::notice::»).

    python -m podcast.diagnostico elpais     → qué ve el robot de El País Exprés
    python -m podcast.diagnostico noticias   → abre el noticiario y cuenta lo que trae
    python -m podcast.diagnostico voz        → prueba corta de la voz de Gemini (una y dos voces), Edge y Piper
    python -m podcast.diagnostico edge|piper → solo una de las voces de reserva (no gastan cupo de Gemini)
    python -m podcast.diagnostico vozlarga   → una tanda larga, como las del episodio (1 petición si va bien)
    python -m podcast.diagnostico guion      → pide un guion de prueba a Gemini con noticias inventadas
    python -m podcast.diagnostico planes     → propuesta del momento Distinto Básico (va a Dropbox /Pruebas)
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


def planes():
    """Momento Distinto Básico de prueba: la propuesta va a Dropbox (/Pruebas), aquí solo datos técnicos."""
    from . import planes as pl, dropbox, config, util
    token = dropbox.token_acceso()
    crit = dropbox.descargar(token, config.DROPBOX_PLANES_CRITERIOS)
    criterios = (crit.decode("utf-8-sig", "replace") if crit else
                 "Planes culturales o de calle en A Coruña para una pareja, de unas tres horas, y comida en un sitio vegano cerca.")
    hist = dropbox.descargar(token, config.DROPBOX_PLANES_HISTORIAL)
    historial = [l for l in (hist.decode("utf-8-sig", "replace").splitlines() if hist else []) if l.strip()]
    t0 = time.time()
    plan, avisos = pl.proponer(util.ahora().date(), criterios, historial)
    if plan:
        dropbox.subir(token, "/Pruebas/plan de prueba.json", json.dumps(plan, ensure_ascii=False, indent=1).encode("utf-8-sig"))
    nota("Distinto Básico", f"{time.time() - t0:.0f}s · {'propuesta OK' if plan else 'sin propuesta'} · "
                            f"modelo {plan.get('modelo') if plan else '-'} · fuentes {len(plan.get('fuentes', [])) if plan else 0} · "
                            f"criterios {'de Dropbox' if crit else 'genéricos'} · páginas: {plan.get('lectura') if plan else '-'} · "
                            f"fecha propuesta {plan.get('dia') if plan else '-'} · avisos: {avisos}"[:3000])


TURNOS_PRUEBA = [
    "El Tribunal Supremo ha dejado sin voto a más de ciento sesenta mil personas que se nacionalizaron con la ley de nietos.",
    "¿Y eso por qué?",
    "Porque considera que la instrucción de Justicia no se ajusta a la ley. Y ojo, que la decisión no fue unánime.",
    "Una magistrada firmó un voto discrepante muy duro, diciendo que el daño es irreparable.",
    "¡No me digas!",
    "Los Reyes visitan hoy Ceuta, dos meses después de la entrada de unas ochenta mil personas.",
    "La normalidad todavía queda lejos, dicen los vecinos, aunque las playas ya están despejadas.",
    "El Fondo Monetario Internacional sube la previsión de crecimiento de España hasta el dos coma cinco por ciento.",
    "Eso es una buena noticia, ¿no?",
    "Sí, aunque la deuda pública sigue siendo nuestro talón de Aquiles si los tipos no bajan.",
    "Un vecino de A Coruña tendrá que repartir un premio de lotería con su exmujer.",
    "Vaya puntería.",
    "La Audiencia Provincial dice que, como no estaban divorciados, el premio va a medias.",
    "Y en ciencia, unos microrobots que se recargan simplemente caminando sobre el suelo.",
    "Mide apenas un milímetro cuadrado y tiene un grosor de ciento treinta y cinco micrómetros.",
    "Tal cual.",
]


def cortes():
    """Una tanda de una voz como las del episodio: se corta en turnos y luego cada trozo se transcribe
    por separado para ver si empieza y acaba donde debe (solo cifras)."""
    from . import voces, alinear, config
    via, modelo = config.MODELOS_VOZ[0]
    lote = list(enumerate(TURNOS_PRUEBA))
    t0 = time.time()
    try:
        piezas = voces._voz_con_modelo(via, modelo, "A", [lote])
    except Exception as e:
        nota("Cortes", f"FALLO {modelo}: {str(e)[:600]} · registro: " + " | ".join(voces.REGISTRO[-6:]), "warning")
        return
    malos = []
    m = alinear._modelo()
    for i, texto in lote:
        x = alinear.a_mono16k(piezas[i])
        segs, _ = m.transcribe(x, language="es", beam_size=1, vad_filter=False) if m else ([], None)
        oido = "".join(alinear.norma(" ".join(sg.text for sg in segs)))
        esperado = "".join(alinear.norma(texto))
        import difflib
        # sin espacios ni signos: el principio y el final de lo oído tienen que parecerse a los del turno
        ok_ini = difflib.SequenceMatcher(None, oido[:8], esperado[:8]).ratio() >= 0.6
        ok_fin = difflib.SequenceMatcher(None, oido[-8:], esperado[-8:]).ratio() >= 0.6
        if not (ok_ini and ok_fin):
            malos.append(f"turno {i + 1}: oído «{oido[:12]} … {oido[-12:]}» (esperado «{esperado[:12]} … {esperado[-12:]}»)")
    nota("Cortes", f"{modelo} ({via}) · {len(lote)} turnos en {time.time() - t0:.0f}s · trozos mal cortados: {len(malos)} · "
                   f"{' | '.join(malos)} · registro: " + " | ".join(voces.REGISTRO[-4:]))


def busqueda():
    """¿Qué herramientas de búsqueda deja usar el plan gratuito? (solo datos técnicos)"""
    import os
    import requests
    clave = os.environ.get("GEMINI_API_KEY", "")
    cab = {"x-goog-api-key": clave, "Content-Type": "application/json"}
    pregunta = "¿Qué conciertos hay en A Coruña esta semana? Responde en dos líneas."
    pruebas = [
        ("generate · google_search", "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
         {"contents": [{"parts": [{"text": pregunta}]}], "tools": [{"google_search": {}}]}),
        ("interactions · google_search", "https://generativelanguage.googleapis.com/v1beta/interactions",
         {"model": "gemini-3.8-flash", "input": pregunta, "tools": [{"type": "google_search"}]}),
        ("generate · url_context", "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
         {"contents": [{"parts": [{"text": "Resume en dos líneas qué eventos hay en https://www.coruna.gal/cultura/es/agenda"}]}],
          "tools": [{"url_context": {}}]}),
        ("generate · google_search · 2.5-flash", "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
         {"contents": [{"parts": [{"text": pregunta}]}], "tools": [{"google_search": {}}]}),
    ]
    for nombre, url, cuerpo in pruebas:
        t0 = time.time()
        try:
            r = requests.post(url, json=cuerpo, headers=cab, timeout=120)
            texto = r.text
            if r.status_code == 200:
                j = r.json()
                fuentes = len(re.findall(r'"uri"', texto))
                nota(f"Búsqueda {nombre}", f"OK en {time.time() - t0:.0f}s · {fuentes} enlaces de fuentes · {len(texto)} bytes")
            else:
                nota(f"Búsqueda {nombre}", f"HTTP {r.status_code} en {time.time() - t0:.0f}s · {texto[:1800]}", "warning")
        except Exception as e:
            nota(f"Búsqueda {nombre}", f"FALLO {e}", "warning")


VOCES_MUESTRA = ["Charon", "Algenib", "Algieba", "Orus"]   # voces graves de hombre de Gemini
TEXTO_MUESTRA = ("Hoy es jueves, quince de octubre. Empezamos con los titulares. El Gobierno ha presentado esta "
                 "mañana su plan de vivienda, y la idea es que llegue a los alquileres antes del verano. Y ojo, "
                 "porque en Coruña también hay novedades: el puerto abre por fin el paseo nuevo de la dársena.")


def muestras():
    """Una muestra corta de cada voz candidata (1 petición por voz), en MP3 en Dropbox
    /Pruebas/Voces para Martín/, para elegir de oído."""
    import os
    import subprocess
    from . import voces, config, dropbox
    via, modelo = config.MODELOS_VOZ[0]
    lista = [v.strip() for v in (os.environ.get("VOCES_MUESTRA") or ",".join(VOCES_MUESTRA)).split(",") if v.strip()]
    token = dropbox.token_acceso()
    for n, nombre_voz in enumerate(lista, 1):
        config.LOCUTORES["B"]["gemini"] = nombre_voz
        tanda = {"bloque": "titulares", "turnos": [{"voz": "B", "texto": TEXTO_MUESTRA}]}
        t0 = time.time()
        try:
            wav = voces._llamada(via, modelo, tanda)
            mp3 = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
                                  "-af", "loudnorm=I=-16:TP=-1.5", "-c:a", "libmp3lame", "-b:a", "128k",
                                  "-f", "mp3", "pipe:1"], input=wav, capture_output=True, check=True).stdout
            dropbox.subir(token, f"/Pruebas/Voces para Martín/{n} {nombre_voz}.mp3", mp3)
            nota(f"Muestra {nombre_voz}", f"OK en {time.time() - t0:.0f}s · {voces.duracion_wav(wav):.1f}s · {modelo}")
        except Exception as e:
            nota(f"Muestra {nombre_voz}", f"FALLO {modelo}: {str(e)[:500]}", "warning")


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
             "piper": piper, "vozlarga": vozlarga, "planes": planes, "busqueda": busqueda, "cortes": cortes,
             "muestras": muestras}[prueba]()
        except Exception as e:
            nota(f"Diagnóstico {prueba}", traceback.format_exc()[-1500:], "warning")
