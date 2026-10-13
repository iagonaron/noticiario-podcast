"""El robot completo: noticias → lo rápido del día → conversación → voces → montaje → Dropbox."""
import json
import os
import sys
import tempfile
import threading
import time
import traceback

from . import agenda, config, cumples, dropbox, festivos, guion, montaje, noticias, planes, tiempo, util, voces

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "..", "salida")


ESTADO = {"etapa": "inicio", "t0": time.time(), "diag": [], "avisos": [], "token": None}


def etapa(nombre):
    ESTADO["etapa"] = nombre
    ESTADO["diag"].append(f"[{time.time() - ESTADO['t0']:.0f}s] {nombre}")
    util.log(f"— {nombre}")


def anotar(nivel, titulo, texto):
    texto = str(texto).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::{nivel} title={titulo}::{texto[:3000]}", flush=True)


def resumen_github(lineas):
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")


def recoger_noticias(hoy, diag):
    """Noticias del noticiario. Si la Portada sale vacía, se reintenta enseguida; si sale de ayer
    (El País aún no ha publicado la de hoy) y es por la mañana temprano, se espera unos minutos."""
    datos, avisos = None, []
    for intento in range(3):
        try:
            d = noticias.recoger()
            diag.append(f"Noticiario (intento {intento + 1}): {d.get('carga')} · portada {len(d['portada'])}, "
                        f"interés {len(d['interes'])}, local {len(d['local'])}")
            if datos is None or len(d["portada"]) >= len(datos["portada"]):
                datos = d
        except Exception as e:
            avisos.append(f"No se pudo leer el noticiario (intento {intento + 1}): {e}"[:300])
            util.log(avisos[-1])
            continue
        if not datos["portada"]:
            continue                                   # vacía: probar otra vez ya
        if noticias.portada_es_de_hoy(datos, hoy) or not (6 <= util.ahora().hour < 9):
            break
        util.log("La Portada (El País Exprés) aún es de ayer: espero 5 minutos y vuelvo a mirar")
        time.sleep(300)
    if datos is None:
        datos = {"portada": [], "interes": [], "local": [], "alertas_sanitarias": [], "avisos_aemet": [], "madrid": None}
    if not datos["portada"]:
        avisos.append("No se pudo leer la Portada de El País Exprés.")
    elif not noticias.portada_es_de_hoy(datos, hoy):
        avisos.append("La Portada de El País Exprés aún era la de ayer.")
    return datos, avisos


def lo_rapido(textos, primera_voz):
    """Cumpleaños y festivos, agenda y tiempo, alternando voces. Plantilla fija, sin IA."""
    segs, voz = [], primera_voz
    for t in textos:
        if t:
            segs.append({"bloque": "rapido", "noticia": 0, "voz": voz, "texto": t})
            voz = "B" if voz == "A" else "A"
    return segs


def plan_del_dia(token, hoy, diag):
    """Momento Distinto Básico: criterios e historial desde Dropbox y propuesta de Gemini."""
    if not token:
        return None, [], ["Distinto Básico: sin Dropbox no hay criterios"]
    crit = dropbox.descargar(token, config.DROPBOX_PLANES_CRITERIOS)
    if not crit:
        return None, [], [f"Distinto Básico: no está {config.DROPBOX_PLANES_CRITERIOS} en la carpeta del pódcast"]
    hist = dropbox.descargar(token, config.DROPBOX_PLANES_HISTORIAL)
    historial = [l for l in (hist.decode("utf-8-sig", "replace").splitlines() if hist else []) if l.strip()]
    plan, avisos = planes.proponer(hoy, crit.decode("utf-8-sig", "replace"), historial)
    diag.append(f"Distinto Básico: {'propuesta de ' + plan.get('modelo', '?') if plan else 'sin propuesta'} · "
                f"{len(historial)} propuestas anteriores")
    return plan, historial, avisos


def apuntar_plan(token, hoy, plan, historial):
    lineas = historial + [planes.linea_historial(hoy, plan)]
    texto = "\n".join(lineas[-400:]) + "\n"
    dropbox.subir(token, config.DROPBOX_PLANES_HISTORIAL, texto.encode("utf-8-sig"))


def main():
    t0 = time.time()
    ahora = util.ahora()
    hoy = ahora.date()
    os.makedirs(SALIDA, exist_ok=True)
    avisos, diag = ESTADO["avisos"], ESTADO["diag"]
    diag.append(f"Ejecución: {ahora:%Y-%m-%d %H:%M} (Madrid)")
    util.log(f"Noticiario de {util.fecha_larga(ahora)} · empiezo")

    token = None
    etapa("Dropbox")
    try:
        token = dropbox.token_acceso()
        ESTADO["token"] = token
    except Exception as e:
        avisos.append(f"Dropbox: {e}")
        util.log(avisos[-1])

    # 0) el plan del Distinto Básico se busca en paralelo (leer agendas tarda unos minutos)
    resultado_plan = {}

    def buscar_plan():
        try:
            resultado_plan["v"] = plan_del_dia(token, hoy, [])
        except Exception as e:
            resultado_plan["error"] = f"{type(e).__name__}: {e}"[:300]

    hilo_plan = threading.Thread(target=buscar_plan, daemon=True)
    hilo_plan.start()

    # 1) noticias
    etapa("noticias")
    datos, av = recoger_noticias(hoy, diag)
    avisos += av
    diag += ["Fuentes del noticiario:"] + [f"  {l}" for l in (datos.get("diagnostico") or [])]
    util.log(f"Noticias: portada {len(datos['portada'])}, interés {len(datos['interes'])}, local {len(datos['local'])}")

    # 2) lo rápido: cumpleaños y festivos, agenda, tiempo
    etapa("tiempo, agenda, cumpleaños y festivos")
    horas, fuente_tiempo, av, mg = tiempo.obtener_horas(hoy)
    avisos += av
    resumen_t = tiempo.resumir(horas, mg, datos.get("avisos_aemet"))
    texto_tiempo = tiempo.texto_breve(horas, resumen_t)
    diag.append(f"Tiempo: {fuente_tiempo} · {len(horas)} horas")

    eventos, av = agenda.obtener(hoy)
    avisos += av
    texto_agenda = agenda.texto_plantilla(eventos, av)
    diag.append(f"Agenda: hoy {len(eventos['hoy'])} · mañana {len(eventos['manana'])} · avisos {len(av)}")

    texto_dias = ""
    if token:
        try:
            lista = dropbox.descargar(token, config.DROPBOX_CUMPLES)
            if lista is None:
                avisos.append(f"No encuentro {config.DROPBOX_CUMPLES} en la carpeta del pódcast.")
            else:
                texto_dias = cumples.texto(cumples.leer(lista.decode("utf-8-sig", "replace")), hoy)
        except Exception as e:
            avisos.append(f"Cumpleaños: no se pudo leer la lista ({type(e).__name__})")
    try:
        texto_dias = (texto_dias + " " + festivos.texto(hoy)).strip()
    except Exception as e:
        avisos.append(f"Festivos: {type(e).__name__}: {e}"[:200])

    # 3) la conversación: fecha y lo rápido (plantillas) + noticias (IA) + Distinto Básico + cierre
    etapa("guion")
    segs_ia, info = guion.escribir(ahora, datos)
    avisos += info.get("avisos", [])
    inicio = guion.apertura(ahora) + lo_rapido([texto_dias, texto_agenda, texto_tiempo], "B")
    segs = inicio + segs_ia

    etapa("Distinto Básico")
    hilo_plan.join(timeout=max(5, config.PLAN_ESPERA_MAX - (time.time() - t0)))
    plan, historial_planes = None, []
    if "v" in resultado_plan:
        plan, historial_planes, av = resultado_plan["v"]
        avisos += av
    elif "error" in resultado_plan:
        avisos.append(f"Distinto Básico: {resultado_plan['error']}")
    else:
        avisos.append("Distinto Básico: la propuesta no llegó a tiempo; hoy va sin ella")
    diag.append(f"Distinto Básico: {'propuesta de ' + plan.get('modelo', '?') if plan else 'sin propuesta'}"
                + (f" · páginas: {plan.get('lectura')}" if plan else ""))
    if plan:
        numero = max([s.get("noticia") or 0 for s in segs_ia] + [0]) + 1
        primera = "B" if segs[-1]["voz"] == "A" else "A"
        segs_db, modelo_db, av = guion.escribir_distinto(plan, primera, numero)
        avisos += av
        segs += segs_db
        info["plan_fuentes"] = [u for u in ([plan.get("fuente")] + plan.get("fuentes", [])) if u]
        diag.append(f"Distinto Básico (guion): {modelo_db} · {len(segs_db)} turnos")
    segs += guion.cierre(segs[-1]["voz"])
    info["palabras"] = sum(util.palabras(s["texto"]) for s in segs)
    util.log(f"Guion: {info.get('modelo')} · {info['palabras']} palabras · {len(segs)} turnos")
    diag.append(f"Guion: {info.get('modelo')} · {info['palabras']} palabras · {len(segs)} turnos · {info.get('dialogo', '')}")

    # 5) voces, música y montaje
    with tempfile.TemporaryDirectory() as tmp:
        etapa("voces")
        try:
            piezas, motor, av = voces.sintetizar(segs, tmp)
        finally:
            diag += ["Registro de voz:"] + [f"  {l}" for l in voces.REGISTRO]
        avisos += av
        util.log(f"Voces: {motor} · {len(piezas)} piezas")
        diag.append(f"Voces: {motor} · {len(piezas)} piezas")
        for clave in sorted({p["voz"] for p in piezas}):
            mias = [p for p in piezas if p["voz"] == clave]
            pal, seg = sum(p["palabras"] for p in mias), sum(p["segundos"] for p in mias)
            diag.append(f"  voz {clave}: {len(mias)} turnos · {pal} palabras · {seg:.0f} s ({pal / max(seg, 1) * 60:.0f} p/min)")

        de_dropbox = {}
        if token:
            try:
                for e in dropbox.listar(token, config.DROPBOX_MUSICA):
                    nombre, ext = os.path.splitext(e.get("name", "").lower())
                    if nombre in montaje.PIEZAS and ext in (".mp3", ".wav", ".m4a", ".aif", ".aiff"):
                        de_dropbox[nombre] = dropbox.descargar(token, e["path_lower"])
            except Exception as e:
                avisos.append(f"Música de Dropbox: {e}"[:300])
        etapa("montaje")
        musica = montaje.cargar_musica(de_dropbox)
        diag.append(f"Música: {', '.join(sorted(musica)) or 'ninguna'}")
        wav = os.path.join(tmp, "programa.wav")
        duracion = montaje.montar(piezas, musica, wav)
        mp3 = os.path.join(SALIDA, "Noticiario de hoy.mp3")
        titulo = f"Noticiario · {util.fecha_larga(ahora)}"
        montaje.a_mp3(wav, mp3, {"title": titulo, "artist": "Noticiario de Iago", "album": "Noticiario de Iago",
                                 "date": hoy.isoformat(), "comment": f"Voz: {motor} · Guion: {info.get('modelo')}"})
    util.log(f"Programa montado: {duracion / 60:.1f} minutos")
    diag.append(f"Duración: {duracion / 60:.1f} min · total de la ejecución {(time.time() - t0) / 60:.1f} min")

    extra = f" · voz: {motor} · {duracion / 60:.1f} min · generado a las {util.ahora():%H:%M}"
    md = guion.a_markdown(segs, dict(info, avisos=avisos), ahora, extra)
    with open(os.path.join(SALIDA, "Guion de hoy.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(SALIDA, "datos.json"), "w", encoding="utf-8") as f:
        json.dump({"tiempo": resumen_t, "horas": horas, "noticias": datos}, f, ensure_ascii=False, indent=1, default=str)

    # 5) a Dropbox
    etapa("subida a Dropbox")
    subido = False
    if token:
        with open(mp3, "rb") as f:
            dropbox.subir(token, config.DROPBOX_MP3, f.read())
        dropbox.subir(token, config.DROPBOX_GUION, md.encode("utf-8-sig"))
        subido = True
        util.log("Subido a Dropbox")
        if plan and not config.PRUEBA:
            try:
                apuntar_plan(token, hoy, plan, historial_planes)
            except Exception as e:
                avisos.append(f"Distinto Básico: no se pudo apuntar la propuesta ({type(e).__name__})")
        try:
            texto_diag = "\n".join(diag + ["", "Avisos:"] + [f"  - {a}" for a in avisos])
            dropbox.subir(token, config.DROPBOX_DIAGNOSTICO, texto_diag.encode("utf-8-sig"))
        except Exception:
            pass

    # OJO: el repositorio es público → aquí solo datos técnicos, nada de agenda, nombres ni noticias
    resumen_github([
        f"## 🎙️ {titulo}",
        f"- Duración: **{duracion / 60:.1f} min** · voz: **{motor}** · guion: **{info.get('modelo')}** · {info.get('palabras')} palabras",
        f"- Tiempo: {fuente_tiempo} · noticias: {len(datos['portada'])}+{len(datos['interes'])}+{len(datos['local'])}",
        f"- Dropbox: {'✅ subido' if subido else '⚠️ NO subido'} · tardó {(time.time() - t0) / 60:.1f} min",
        f"- Avisos: {len(avisos)} (el detalle está en «Diagnóstico.txt», en tu Dropbox)",
    ])
    anotar("notice", "Episodio", f"{duracion / 60:.1f} min · voz {motor} · guion {info.get('modelo')} · "
                                  f"{info.get('palabras')} palabras · noticias {len(datos['portada'])}+{len(datos['interes'])}+"
                                  f"{len(datos['local'])} · avisos {len(avisos)} · {(time.time() - t0) / 60:.1f} min · "
                                  + " | ".join(l for l in diag if l.startswith("[")))
    anotar("notice", "Voz", "\n".join(voces.REGISTRO[-40:]))
    if not subido:
        util.log("⚠️ El MP3 no se subió a Dropbox.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        traza = traceback.format_exc()
        print(traza, flush=True)
        donde = [l.strip() for l in traza.splitlines() if l.strip().startswith('File "') and "/podcast/" in l]
        anotar("error", "El noticiario falló",
               f"Etapa: {ESTADO['etapa']} · {time.time() - ESTADO['t0']:.0f}s · {type(e).__name__}: {str(e)[:400]} · "
               f"{donde[-1] if donde else ''}")
        if voces.REGISTRO:
            anotar("warning", "Voz", "\n".join(voces.REGISTRO[-40:]))
        if ESTADO.get("token"):
            try:
                texto = "\n".join(ESTADO["diag"] + ["", "Avisos:"] + [f"  - {a}" for a in ESTADO["avisos"]]
                                  + ["", "ERROR:", traza])
                dropbox.subir(ESTADO["token"], config.DROPBOX_DIAGNOSTICO, texto.encode("utf-8-sig"))
            except Exception:
                pass
        resumen_github(["## ⚠️ El noticiario de hoy falló", f"Etapa: {ESTADO['etapa']}"])
        sys.exit(1)
