"""Diagnóstico técnico (sin datos personales). Resultados como anotaciones de GitHub («::notice::»).

    python -m podcast.diagnostico elpais     → qué ve el robot de El País Exprés
    python -m podcast.diagnostico noticias   → abre el noticiario y cuenta lo que trae
    python -m podcast.diagnostico voz        → prueba corta de la voz de Gemini (una y dos voces), Edge y Piper
    python -m podcast.diagnostico edge|piper → solo una de las voces de reserva (no gastan cupo de Gemini)
    python -m podcast.diagnostico vozlarga   → una tanda larga, como las del episodio (1 petición si va bien)
    python -m podcast.diagnostico guion      → pide un guion de prueba a Gemini con noticias inventadas
    python -m podcast.diagnostico planes     → propuesta del momento Distinto Básico (va a Dropbox /Pruebas)
    python -m podcast.diagnostico pronuncia  → cómo dicen las voces la x gallega (1 petición por voz; MP3 en
                                               Dropbox /Pruebas/Pronunciación/)
    python -m podcast.diagnostico fricativas → mide el «soplo» de la x en esos MP3 (sin gastar cupo)
    python -m podcast.diagnostico pausas     → cuánto silencio traen los lotes guardados (CRUDO; sin cupo)
    python -m podcast.diagnostico historia   → recupera el Diagnóstico y el guion de otro día (FECHA; sin cupo)
"""
import io
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
    """Una tanda de una voz como las del episodio (1 petición): se corta en turnos y luego cada trozo se
    transcribe por separado para ver si empieza y acaba donde debe. Con SIN_ETIQUETA=si se pide sin la
    etiqueta de pausa entre turnos (el caso difícil). El lote queda en Dropbox para «recortar»."""
    import json
    import os
    import subprocess
    from . import voces, alinear, config, dropbox
    via, modelo = config.MODELOS_VOZ[0]
    if (os.environ.get("SIN_ETIQUETA") or "").lower() in ("si", "sí", "1", "true"):
        voces.SIN_PAUSAS.add(modelo)
    lote = list(enumerate(TURNOS_PRUEBA))
    t0 = time.time()
    try:
        piezas = voces._voz_con_modelo(via, modelo, "A", [lote])
    except Exception as e:
        nota("Cortes", f"FALLO {modelo}: {str(e)[:600]} · registro: " + " | ".join(voces.REGISTRO[-6:]), "warning")
        return
    m = alinear._modelo()
    cuentas = {}
    for i, texto in lote:
        segs, _ = m.transcribe(alinear.a_mono16k(piezas[i]), language="es", beam_size=1, vad_filter=False,
                               condition_on_previous_text=False) if m else ([], None)
        oido = alinear.norma(" ".join(sg.text for sg in segs))
        previo = alinear.norma(TURNOS_PRUEBA[i - 1]) if i > 0 else []
        siguiente = alinear.norma(TURNOS_PRUEBA[i + 1]) if i + 1 < len(TURNOS_PRUEBA) else []
        problemas = _bordes(oido, alinear.norma(texto), previo, siguiente)
        largos = _huecos(piezas[i])
        if largos:
            problemas.append("hueco")
        for p in problemas:
            cuentas[p] = cuentas.get(p, 0) + 1
            if p != "hueco":
                print(f"turno {i + 1}: {p} · oído «{' '.join(oido)}»", flush=True)
    try:
        token = dropbox.token_acceso()
        carpeta = "/Pruebas/Crudo del diagnóstico"
        lista = []
        for k, c in enumerate(voces.CRUDOS, 1):
            mp3 = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-c:a", "libmp3lame",
                                  "-b:a", "96k", "-f", "mp3", "pipe:1"], input=c["wav"], capture_output=True, check=True).stdout
            dropbox.subir(token, f"{carpeta}/lote {k}.mp3", mp3)
            lista.append(dict({k2: v for k2, v in c.items() if k2 != "wav"}, fichero=f"lote {k}.mp3"))
        dropbox.subir(token, f"{carpeta}/lotes.json", json.dumps({"lotes": lista}, ensure_ascii=False).encode("utf-8"))
    except Exception as e:
        nota("Cortes", f"no se pudo guardar el lote: {e}"[:300], "warning")
    nota("Cortes", f"{modelo} ({via}) · pausas {modelo not in voces.SIN_PAUSAS} · {len(lote)} turnos en "
                   f"{time.time() - t0:.0f}s · problemas: {cuentas or 'ninguno'} · registro: " + " | ".join(voces.REGISTRO[-3:]))


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


FRASES_X = [
    "La Xunta de Galicia presentó hoy el plan del Xacobeo.",
    "En Arteixo, Sanxenxo y Rianxo se esperan lluvias por la tarde.",
    "Xosé y Uxía viven en Muxía, cerca de Laxe.",
    "Y esto no cambia: el taxi salió de México con un examen de xilófono.",
]


def pronuncia():
    """Cómo dicen las voces la x gallega (1 petición por voz, con el primer modelo de MODELOS_VOZ).
    Cada voz lee primero la frase de la Xunta tal cual (como hasta el 17-oct-2026) y luego todas
    como se les escriben ahora (pronuncia.py). Deja un MP3 por voz y un informe en Dropbox
    /Pruebas/Pronunciación/; en la anotación, qué entiende Whisper de cada frase."""
    import subprocess
    import numpy as np
    from . import voces, alinear, config, dropbox, util, pronuncia as pr
    via, modelo = config.MODELOS_VOZ[0]
    textos = [FRASES_X[0]] + [pr.para_voz(f) for f in FRASES_X]
    token = dropbox.token_acceso()
    m = alinear._modelo()
    informe = [f"Prueba de pronunciación · {modelo} ({via}) · {util.ahora():%d-%m-%Y %H:%M}",
               "La frase 1 va escrita como antes («Xunta»); las demás, como se les escriben ahora a las voces.", ""]
    for clave in ("A", "B"):
        nombre_voz = f"{voces.nombre(clave)} ({config.LOCUTORES[clave]['gemini']})"
        voces.CRUDOS.clear()
        t0 = time.time()
        try:
            piezas = voces._voz_con_modelo(via, modelo, clave, [list(enumerate(textos))])
        except Exception as e:
            nota(f"Pronunciación {nombre_voz}", f"FALLO {modelo}: {str(e)[:500]}", "warning")
            informe += [f"{nombre_voz}: no salió ({str(e)[:200]})", ""]
            continue
        informe.append(f"{nombre_voz} · {time.time() - t0:.0f}s:")
        for i, t in enumerate(textos):
            oido = ""
            if m:
                segs, _ = m.transcribe(alinear.a_mono16k(piezas[i]), language="es", beam_size=1,
                                       vad_filter=False, condition_on_previous_text=False)
                oido = " ".join(sg.text.strip() for sg in segs)
            informe.append(f"  {i + 1}. escrito: {t}\n     oído:    {oido}")
        # lo que dijo Gemini tal cual (sin cortar); si el lote se partió, los trozos seguidos
        crudos = [c["wav"] for c in voces.CRUDOS if c["voz"] == clave and c["tramos"]] or [piezas[i] for i in range(len(textos))]
        silencio = np.zeros(int(alinear.SR * 0.8), np.float32)
        x = np.concatenate([np.concatenate([alinear.a_mono16k(w), silencio]) for w in crudos])
        pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()
        mp3 = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "s16le", "-ar", str(alinear.SR),
                              "-ac", "1", "-i", "pipe:0", "-af", "loudnorm=I=-16:TP=-1.5", "-c:a", "libmp3lame",
                              "-b:a", "128k", "-f", "mp3", "pipe:1"], input=pcm, capture_output=True, check=True).stdout
        dropbox.subir(token, f"/Pruebas/Pronunciación/{voces.nombre(clave)}.mp3", mp3)
        informe.append("")
    dropbox.subir(token, "/Pruebas/Pronunciación/informe.txt", "\n".join(informe).encode("utf-8"))
    nota("Pronunciación", "\n".join(informe))


def fricativas():
    """Mide, sin gastar cupo, cómo suena el «soplo» de cada palabra en los MP3 de «pronuncia»
    (Whisper sitúa las palabras; luego se mira el espectro cada 10 ms). La frecuencia central del
    soplo distingue los sonidos: «s» ≈ 5-6 kHz, «sh» ≈ 2,5-4 kHz, jota ≈ 1,5-2,5 kHz; la «y» de
    «Yunta» es sonora y casi no tiene soplo. Así se compara la frase de antes con la de ahora."""
    import subprocess
    import numpy as np
    from . import alinear, dropbox
    token = dropbox.token_acceso()
    m = alinear._modelo()
    sr, n, hop = 16000, 512, 160
    informe = ["Soplo de cada palabra (frecuencia central y duración). Referencia: s ≈ 5-6 kHz · "
               "sh ≈ 2,5-4 kHz · jota ≈ 1,5-2,5 kHz · la «y» casi no tiene soplo.", ""]
    for nombre_voz in ("Lucía", "Martín"):
        mp3 = dropbox.descargar(token, f"/Pruebas/Pronunciación/{nombre_voz}.mp3")
        if not mp3:
            continue
        pcm = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-f", "s16le",
                              "-ac", "1", "-ar", str(sr), "pipe:1"], input=mp3, capture_output=True, check=True).stdout
        x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
        segs, _ = m.transcribe(x, language="es", word_timestamps=True, beam_size=1, vad_filter=False,
                               condition_on_previous_text=False)
        frases = [[(w.word.strip(), w.start, w.end) for w in (sg.words or [])] for sg in segs]
        tramas = np.lib.stride_tricks.sliding_window_view(np.pad(x, (n // 2, n // 2)), n)[::hop] * np.hanning(n)
        P = np.abs(np.fft.rfft(tramas, axis=1)) ** 2
        f = np.fft.rfftfreq(n, 1 / sr)
        total = P.sum(1) + 1e-12
        db = 10 * np.log10(total)
        soplo = ((P[:, f >= 2000].sum(1) / total > 0.5) & (P[:, f < 1000].sum(1) / total < 0.2)
                 & (db > np.percentile(db, 95) - 40))
        banda = (f >= 1500) & (f <= 7800)
        centro = (P[:, banda] * f[banda]).sum(1) / (P[:, banda].sum(1) + 1e-12)
        informe.append(f"{nombre_voz}:")
        for frase in frases:
            linea = []
            for palabra, a, b in frase:
                i0, i1 = int(max(0.0, a - 0.08) * 100), min(int((b + 0.05) * 100), len(soplo))
                tramos, k = [], i0
                while k < i1:
                    if soplo[k]:
                        j = k
                        while j < i1 and soplo[j]:
                            j += 1
                        if j - k >= 3:
                            tramos.append(f"{np.median(centro[k:j]) / 1000:.1f}k/{(j - k) * 10}ms")
                        k = j
                    else:
                        k += 1
                linea.append(f"{palabra} [{' '.join(tramos)}]" if tramos else palabra)
            if linea:
                informe.append("  " + " ".join(linea))
        informe.append("")
    texto = "\n".join(informe)
    dropbox.subir(token, "/Pruebas/Pronunciación/soplo.txt", texto.encode("utf-8"))
    nota("Fricativas", texto)


def pausas():
    """Cuánto silencio hay en los lotes guardados (CRUDO), en total y en cada corte entre frases.
    Sirve para ver si un lote «demasiado largo» es voz lenta o pausas larguísimas. Sin cupo."""
    import json
    import os
    import subprocess
    import numpy as np
    from . import alinear, dropbox
    carpeta = os.environ.get("CRUDO") or "/Pruebas/Crudo de la prueba"
    token = dropbox.token_acceso()
    meta = json.loads(dropbox.descargar(token, f"{carpeta}/lotes.json").decode("utf-8"))
    lineas = []
    for lote in meta["lotes"]:
        mp3 = dropbox.descargar(token, f"{carpeta}/{lote['fichero']}")
        wav = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", "24000",
                              "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"], input=mp3, capture_output=True, check=True).stdout
        x = alinear.a_mono16k(wav)
        sil, _ = alinear.silencios(alinear.envolvente_db(x), minimo_s=0.3)
        dur = len(x) / alinear.SR
        largos = [d for _, _, d in sil if d >= 0.8]
        en_cortes = [next((d for s0, s1, d in sil if s0 - 0.05 <= b <= s1 + 0.05), 0.0) for _, b in lote["tramos"][:-1]]
        lineas.append(f"{lote['fichero']} · voz {lote['voz']} · {len(lote['tramos'])} turnos · {dur:.0f}s · "
                      f"silencio total {sum(d for _, _, d in sil):.0f}s · silencios de 0,8s o más: {len(largos)} "
                      f"(máx {max(largos, default=0):.1f}s) · en los cortes: mediana "
                      f"{float(np.median(en_cortes)) if en_cortes else 0:.1f}s, máx {max(en_cortes, default=0):.1f}s")
    nota("Pausas", "\n".join(lineas))


def historia():
    """Recupera de Dropbox la versión de otro día (FECHA, por defecto ayer) de «Diagnóstico.txt» y de
    «Guion de hoy.md», que cada episodio sobrescribe, y la deja en /Pruebas/Historia/. Aquí solo se
    anotan horas y tamaños (el contenido puede ser personal). Sin cupo."""
    import datetime as dt
    import os
    from zoneinfo import ZoneInfo
    from . import config, dropbox, util
    fecha = (os.environ.get("FECHA") or "").strip() or (util.ahora().date() - dt.timedelta(days=1)).isoformat()
    token = dropbox.token_acceso()
    madrid = ZoneInfo(config.ZONA)

    def cuando(r):
        return dt.datetime.fromisoformat(r["server_modified"].replace("Z", "+00:00")).astimezone(madrid)

    for ruta in (config.DROPBOX_DIAGNOSTICO, config.DROPBOX_GUION):
        del_dia = sorted((r for r in dropbox.revisiones(token, ruta) if cuando(r).date().isoformat() == fecha),
                         key=cuando)
        if not del_dia:
            nota("Historia", f"{ruta}: no hay ninguna versión del {fecha}", "warning")
            continue
        r = del_dia[-1]
        datos = dropbox.descargar(token, "rev:" + r["rev"])
        base, ext = ruta.strip("/").rsplit(".", 1)
        destino = f"/Pruebas/Historia/{base.split('/')[-1]} del {fecha}.{ext}"
        dropbox.subir(token, destino, datos)
        nota("Historia", f"{ruta} del {fecha}: {len(del_dia)} versiones ese día "
                         f"({', '.join(f'{cuando(x):%H:%M}' for x in del_dia)}); la de las {cuando(r):%H:%M} "
                         f"({len(datos)} bytes) → {destino}")


def tiempo():
    """El tiempo de hoy hora a hora como lo ve el robot (cielo, probabilidad, litros) y la frase que
    saldría en el pódcast. Sin cupo y sin datos personales."""
    from . import tiempo as t, util
    hoy = util.ahora().date()
    horas, fuente, problemas, mg = t.obtener_horas(hoy)
    filas = [f"{o['h']:02d}h · {t.WMO_TEXTO.get(int(o['wcode']), o['wcode']) if isinstance(o.get('wcode'), (int, float)) else '?'}"
             f" · {o.get('prob')}% · {o.get('lluvia')} mm · franja MG {o.get('prob_franja')}%" for o in horas]
    r = t.resumir(horas, mg)
    nota("Tiempo", f"{fuente} · problemas: {problemas or 'ninguno'}\n" + "\n".join(filas)
         + "\n\nFrase del pódcast: " + t.texto_breve(horas, r))


def _parecido(a, b):
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _bordes(oido, esperado, previo, siguiente):
    """Problemas en los bordes de un trozo: «cola» (empieza con el final del turno anterior),
    «invade» (acaba con el principio del siguiente) o «raro» (no empieza o no acaba como debe)."""
    o, e = "".join(oido), "".join(esperado)
    problemas = []
    if _parecido(o[:10], e[:10]) < 0.6:
        cola = any(_parecido("".join(oido[:k]), "".join(previo[-k:])) >= 0.8 for k in (1, 2, 3, 4) if previo)
        problemas.append("cola" if cola else "principio raro")
    if _parecido(o[-10:], e[-10:]) < 0.6:
        invade = any(_parecido("".join(oido[-k:]), "".join(siguiente[:k])) >= 0.8 for k in (1, 2, 3, 4) if siguiente)
        problemas.append("invade" if invade else "final raro")
    return problemas


def _huecos(wav, minimo=0.8):
    """Silencios de más de «minimo» segundos dentro de un trozo (sin contar los bordes)."""
    from . import alinear
    x = alinear.a_mono16k(wav)
    env = alinear.envolvente_db(x)
    sil, _ = alinear.silencios(env, minimo_s=minimo)
    dur = len(x) / alinear.SR
    return [d for s0, s1, d in sil if s0 > 0.05 and s1 < dur - 0.05]


def recortar():
    """Vuelve a cortar los lotes de voz guardados en Dropbox (/Pruebas/Crudo …) con el método actual,
    y compara cada trozo —transcrito por separado— con los cortes que se hicieron en su día.
    No gasta cupo de Gemini. El detalle (con texto) va a Dropbox; aquí solo cifras."""
    import json
    import os
    import subprocess
    from pydub import AudioSegment
    from . import alinear, dropbox
    carpeta = os.environ.get("CRUDO") or "/Pruebas/Crudo de la prueba"
    token = dropbox.token_acceso()
    meta = json.loads(dropbox.descargar(token, f"{carpeta}/lotes.json").decode("utf-8"))
    m = alinear._modelo()
    informe = [f"Recorte de {carpeta} (generado {meta.get('generado')}) · transcripción {config_whisper()}"]
    cuentas = {"antes": {}, "ahora": {}}
    trozos_ahora = {}
    for lote in meta["lotes"]:
        if lote.get("leyo_etiqueta"):
            informe.append(f"\n{lote['fichero']}: leyó la etiqueta de pausa, se salta")
            continue
        mp3 = dropbox.descargar(token, f"{carpeta}/{lote['fichero']}")
        wav = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", "24000",
                              "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"], input=mp3, capture_output=True, check=True).stdout
        textos = lote["textos"]
        try:
            nuevos, resumen = alinear.cortes(wav, textos)
        except Exception as e:
            nuevos, resumen = None, f"ERROR {type(e).__name__}: {e}"
        informe.append(f"\n{lote['fichero']} · voz {lote['voz']} · {lote['modelo']} · pausas {lote['pausas']} · "
                       f"{len(textos)} turnos\n  antes: {lote.get('resumen')}\n  ahora: {resumen}")
        for cuando, tramos in (("antes", lote["tramos"]), ("ahora", nuevos)):
            if not tramos:
                continue
            for i, (a, b) in enumerate(tramos):
                trozo = alinear.recortar(wav, a, b)
                segs, _ = m.transcribe(alinear.a_mono16k(trozo), language="es", beam_size=1, vad_filter=False,
                                       condition_on_previous_text=False) if m else ([], None)
                oido = alinear.norma(" ".join(s.text for s in segs))
                esperado = alinear.norma(textos[i])
                previo = alinear.norma(textos[i - 1]) if i > 0 else []
                siguiente = alinear.norma(textos[i + 1]) if i + 1 < len(textos) else []
                problemas = _bordes(oido, esperado, previo, siguiente)
                largos = _huecos(trozo)
                if largos:
                    problemas.append(f"hueco {max(largos):.1f}s")
                for p in problemas:
                    clave = p.split()[0] if not p.startswith("principio") and not p.startswith("final") else p
                    cuentas[cuando][clave] = cuentas[cuando].get(clave, 0) + 1
                if problemas:
                    informe.append(f"  {cuando} · turno {lote['indices'][i] + 1}: {', '.join(problemas)} · "
                                   f"oído «{' '.join(oido[:5])} … {' '.join(oido[-5:])}» · "
                                   f"esperado «{' '.join(esperado[:5])} … {' '.join(esperado[-5:])}»")
                if cuando == "ahora":
                    trozos_ahora[lote["indices"][i]] = trozo
    # el diálogo recortado, intercalado como en el episodio (sin música), para escucharlo
    if trozos_ahora:
        dialogo = AudioSegment.silent(300, frame_rate=24000)
        for i in sorted(trozos_ahora):
            dialogo += AudioSegment.from_file(io.BytesIO(trozos_ahora[i]), format="wav") + AudioSegment.silent(300, frame_rate=24000)
        b = io.BytesIO()
        dialogo.export(b, format="mp3", bitrate="96k")
        dropbox.subir(token, "/Pruebas/Recorte - diálogo.mp3", b.getvalue())
    resumen = " · ".join(f"{c}: " + (", ".join(f"{k} {v}" for k, v in sorted(cuentas[c].items())) or "nada") for c in cuentas)
    informe.insert(1, f"Problemas por tipo → {resumen}")
    dropbox.subir(token, "/Pruebas/Recorte - informe.txt", "\n".join(informe).encode("utf-8-sig"))
    nota("Recorte", f"{carpeta} · {resumen}")


def timbre():
    """¿Cambia una voz a mitad del programa? Huella de cada trozo (tono, brillo y forma del espectro)
    en el crudo guardado en Dropbox, y los tramos que el robot rehará por sonar distintos (la misma
    regla que usa al generar). Sin gastar cupo. Detalle en Dropbox (/Pruebas/Timbre - informe.txt)."""
    import json
    import os
    import subprocess
    from . import alinear, dropbox, huella
    carpeta = os.environ.get("CRUDO") or "/Pruebas/Crudo del episodio"
    token = dropbox.token_acceso()
    meta = json.loads(dropbox.descargar(token, f"{carpeta}/lotes.json").decode("utf-8"))
    por_voz = {}
    for lote in meta["lotes"]:
        if lote.get("leyo_etiqueta"):
            continue
        mp3 = dropbox.descargar(token, f"{carpeta}/{lote['fichero']}")
        wav = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", "24000",
                              "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"], input=mp3, capture_output=True, check=True).stdout
        x = alinear.a_mono16k(wav)
        for i, (a, b) in enumerate(lote["tramos"]):
            por_voz.setdefault(lote["voz"], {})[lote["indices"][i]] = (huella.huella(x[int(a * 16000):int(b * 16000)]),
                                                                       lote["fichero"])
    resumen, filas = [], []
    for voz, trozos in sorted(por_voz.items()):
        orden = sorted(trozos)
        hs = [trozos[i][0] for i in orden]
        tramos, d = huella.derivas(hs)
        raros = "; ".join(f"turnos {orden[a] + 1}-{orden[b] + 1}" for a, b in tramos) or "ninguno"
        resumen.append(f"voz {voz} · {len(orden)} trozos · tramos que se rehacen: {raros}")
        filas.append(f"\nvoz {voz} · tramos que se rehacen: {raros}")
        for k, i in enumerate(orden):
            h = hs[k]
            if h:
                filas.append(f"  turno {i + 1} ({trozos[i][1]}): distancia {d[k] or 0:.1f} dB · tono {h['tono'] or 0:.0f} · "
                             f"brillo {h['brillo']:.0f} · {h['voz_s']:.1f}s de voz")
    dropbox.subir(token, "/Pruebas/Timbre - informe.txt",
                  ("\n".join([f"Huella de las voces en {carpeta}"] + resumen + filas)).encode("utf-8-sig"))
    nota("Timbre", "\n".join(resumen))


EXPLORAR = r"""
async () => {
  const corta = (t, n) => (t || "").replace(/\s+/g, " ").trim().slice(0, n);
  const out = {state: Object.keys(STATE), secciones: {}, tarjetas: {}};
  for (const [k, v] of Object.entries(STATE.sections || {})) {
    out.secciones[k] = (Array.isArray(v) ? v : []).map(it => ({t: corta(it.title, 160), f: it.source || "",
      c: it.category || "", esp: !!it.isSpecial}));
  }
  for (const [k, v] of Object.entries(STATE.cards || {})) {
    const lista = Array.isArray(v) ? v : (v && (v.items || v.articles || v.list || v.data)) || [];
    out.tarjetas[k] = {tipo: Array.isArray(v) ? "lista" : typeof v,
      claves: (v && typeof v === "object" && !Array.isArray(v)) ? Object.keys(v).slice(0, 25) : [],
      n: Array.isArray(lista) ? lista.length : 0,
      items: (Array.isArray(lista) ? lista : []).slice(0, 40).map(it => ({t: corta(it.title, 160), f: it.source || "",
        c: it.category || ""}))};
  }
  for (const k of Object.keys(STATE)) {
    if (k === "sections" || k === "cards") continue;
    const v = STATE[k];
    out["tipo_" + k] = Array.isArray(v) ? ("lista " + v.length) : typeof v;
  }
  return out;
}
"""


def estado():
    """Qué tiene el noticiario por dentro (secciones y tarjetas con sus titulares), en Dropbox
    /Pruebas/Estado del noticiario.json, para entender de dónde sale cada sección."""
    import json
    from . import dropbox, noticias
    d = noticias.recoger(js=EXPLORAR)
    dropbox.subir(dropbox.token_acceso(), "/Pruebas/Estado del noticiario.json",
                  json.dumps(d, ensure_ascii=False, indent=1).encode("utf-8"))
    nota("Estado del noticiario", f"claves: {d.get('state')} · secciones: "
                                  f"{ {k: len(v) for k, v in d.get('secciones', {}).items()} } · tarjetas: {len(d.get('tarjetas', {}))}")


FUENTES_GALICIA = [
    "https://news.google.com/rss/headlines/section/geo/Galicia?hl=es&gl=ES&ceid=ES:es",
    "https://news.google.com/rss/search?q=Galicia+when:1d&hl=es&gl=ES&ceid=ES:es",
    "https://www.lavozdegalicia.es/rss/",
    "https://www.lavozdegalicia.es/rss/galicia.xml",
    "https://www.lavozdegalicia.es/index.xml",
    "https://www.galiciapress.es/rss",
    "https://www.europapress.es/rss/rss.aspx?ch=00283",
    "https://www.farodevigo.es/rss",
    "https://www.laopinioncoruna.es/rss",
    "https://www.elcorreogallego.es/rss",
    "https://www.crtvg.es/rss/rss-novas.xml",
]


def fuentes_galicia():
    """¿Qué fuentes de noticias de toda Galicia se pueden leer desde aquí (RSS)? Para cada una:
    si responde, cuántas noticias trae y si hablan del terremoto del 15-oct-2026. Detalle en Dropbox."""
    import os
    import urllib.request
    import xml.etree.ElementTree as ET
    from . import dropbox
    urls = (os.environ.get("FUENTES") or "").split() or FUENTES_GALICIA
    resumen, detalle = [], []
    for url in urls:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                cuerpo = r.read()
                estado = r.status
        except Exception as e:
            resumen.append(f"{url} → {str(e)[:60]}")
            continue
        texto = cuerpo.decode("utf-8", "replace")
        titulos = []
        try:
            raiz = ET.fromstring(cuerpo)
            for it in raiz.iter():
                if it.tag.split("}")[-1] in ("item", "entry"):
                    t = next((c.text for c in it if c.tag.split("}")[-1] == "title"), "") or ""
                    titulos.append(t.strip())
        except ET.ParseError:
            enlaces = sorted(set(re.findall(r'href="([^"]+\.xml[^"]*)"', texto)))[:40]
            detalle.append(f"\n{url} (no es RSS; enlaces .xml que trae): " + " | ".join(enlaces))
        sismo = [t for t in titulos if re.search(r"terremoto|se[ií]smo|sismo|tembl", t, re.I)]
        resumen.append(f"{url} → HTTP {estado} · {len(titulos)} noticias · terremoto: {len(sismo)}")
        detalle.append(f"\n{url}\n" + "\n".join(f"  - {t}" for t in titulos[:15]))
    dropbox.subir(dropbox.token_acceso(), "/Pruebas/Fuentes de Galicia.txt",
                  ("\n".join(resumen + detalle)).encode("utf-8-sig"))
    nota("Fuentes de Galicia", "\n".join(resumen))


def galicia():
    """Lo que el robot añadiría hoy como noticias de toda Galicia (las que más medios cuentan)."""
    import json
    from . import dropbox, noticias
    lista = noticias.galicia(maximo=8, minimo_medios=2)
    dropbox.subir(dropbox.token_acceso(), "/Pruebas/Galicia de hoy.json",
                  json.dumps(lista, ensure_ascii=False, indent=1, default=str).encode("utf-8"))
    nota("Galicia", f"{len(lista)} noticias con 2 o más medios · medios: {[n['medios'] for n in lista]}")


def config_whisper():
    from . import config
    return config.WHISPER_MODELO


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
             "muestras": muestras, "recortar": recortar, "timbre": timbre, "estado": estado,
             "fuentes_galicia": fuentes_galicia, "galicia": galicia, "pronuncia": pronuncia,
             "fricativas": fricativas, "pausas": pausas,
             "historia": historia, "tiempo": tiempo}[prueba]()
        except Exception as e:
            nota(f"Diagnóstico {prueba}", traceback.format_exc()[-1500:], "warning")
