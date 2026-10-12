"""El robot completo: noticias → lo rápido del día → conversación → voces → montaje → Dropbox."""
import json
import os
import sys
import tempfile
import time
import traceback

from . import agenda, config, cumples, dropbox, festivos, guion, montaje, noticias, tiempo, util, voces

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
            segs.append({"bloque": "rapido", "voz": voz, "texto": t})
            voz = "B" if voz == "A" else "A"
    return segs


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
                texto_dias = cumples.texto(cumples.leer(lista.decode("utf-8", "replace")), hoy)
        except Exception as e:
            avisos.append(f"Cumpleaños: no se pudo leer la lista ({type(e).__name__})")
    try:
        texto_dias = (texto_dias + " " + festivos.texto(hoy)).strip()
    except Exception as e:
        avisos.append(f"Festivos: {type(e).__name__}: {e}"[:200])

    # 3) la conversación
    etapa("guion")
    segs_ia, info = guion.escribir(ahora, datos)
    avisos += info.get("avisos", [])
    ap = [s for s in segs_ia if s["bloque"] == "apertura"]
    resto = [s for s in segs_ia if s["bloque"] != "apertura"]
    otra = "B" if ap and ap[-1]["voz"] == "A" else "A"
    segs = ap + lo_rapido([texto_dias, texto_agenda, texto_tiempo], otra) + resto
    info["palabras"] = sum(util.palabras(s["texto"]) for s in segs)
    util.log(f"Guion: {info.get('modelo')} · {info['palabras']} palabras · {len(segs)} turnos")
    diag.append(f"Guion: {info.get('modelo')} · {info['palabras']} palabras · {len(segs)} turnos")

    # 4) voces, música y montaje
    with tempfile.TemporaryDirectory() as tmp:
        etapa("voces")
        try:
            unidades, motor, av = voces.sintetizar(segs, tmp)
        finally:
            diag += ["Registro de voz:"] + [f"  {l}" for l in voces.REGISTRO]
        avisos += av
        util.log(f"Voces: {motor} · {len(unidades)} tandas")
        diag.append(f"Voces: {motor} · {len(unidades)} tandas")
        diag += [f"  {u['bloque']:<9} {u['voces']:<2} {u['palabras']:>4} palabras → {u['segundos']:6.1f} s "
                 f"({u['palabras'] / max(u['segundos'], 1) * 60:.0f} p/min)" for u in unidades]

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
        duracion = montaje.montar(unidades, musica, wav)
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
        dropbox.subir(token, config.DROPBOX_GUION, md.encode("utf-8"))
        subido = True
        util.log("Subido a Dropbox")
        try:
            texto_diag = "\n".join(diag + ["", "Avisos:"] + [f"  - {a}" for a in avisos])
            dropbox.subir(token, config.DROPBOX_DIAGNOSTICO, texto_diag.encode("utf-8"))
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
                dropbox.subir(ESTADO["token"], config.DROPBOX_DIAGNOSTICO, texto.encode("utf-8"))
            except Exception:
                pass
        resumen_github(["## ⚠️ El noticiario de hoy falló", f"Etapa: {ESTADO['etapa']}"])
        sys.exit(1)
