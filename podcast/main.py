"""El robot completo: noticias → tiempo → agenda → guion → voces → montaje → Dropbox."""
import datetime as dt
import json
import os
import sys
import tempfile
import time
import traceback

from . import agenda, config, cumples, dropbox, guion, montaje, noticias, tiempo, util, voces

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "..", "salida")


def resumen_github(lineas):
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")


def recoger_noticias(hoy):
    """Noticias del noticiario; si la Portada aún es de ayer, espera un poco y vuelve a mirar."""
    datos, avisos = None, []
    for intento in range(3):
        try:
            datos = noticias.recoger()
        except Exception as e:
            avisos.append(f"No se pudo leer el noticiario (intento {intento + 1}): {e}"[:400])
            util.log(avisos[-1])
            time.sleep(20)
            continue
        if noticias.portada_es_de_hoy(datos, hoy) or intento == 2:
            break
        util.log("La Portada (El País Exprés) aún es de ayer: espero 6 minutos y vuelvo a mirar")
        time.sleep(360)
    if datos is None:
        datos = {"portada": [], "interes": [], "local": [], "alertas_sanitarias": [], "avisos_aemet": [], "madrid": None}
    elif not noticias.portada_es_de_hoy(datos, hoy):
        avisos.append("La Portada de El País Exprés no se había actualizado todavía.")
    return datos, avisos


def main():
    t0 = time.time()
    ahora = util.ahora()
    hoy = ahora.date()
    os.makedirs(SALIDA, exist_ok=True)
    avisos = []
    util.log(f"Noticiario de {util.fecha_larga(ahora)} · empiezo")

    # Dropbox primero: así, si falla, se sabe en el primer minuto
    token = None
    try:
        token = dropbox.token_acceso()
    except Exception as e:
        avisos.append(f"Dropbox: {e}")
        util.log(avisos[-1])

    # 1) noticias, tiempo, agenda y cumpleaños
    datos, av = recoger_noticias(hoy)
    avisos += av
    util.log(f"Noticias: portada {len(datos['portada'])}, interés {len(datos['interes'])}, local {len(datos['local'])}")

    horas, fuente_tiempo, av, mg = tiempo.obtener_horas(hoy)
    avisos += av
    resumen_t = tiempo.resumir(horas, mg, datos.get("avisos_aemet"))
    resumen_t["fuente"] = fuente_tiempo
    util.log(f"Tiempo: {fuente_tiempo}, {len(horas)} horas")

    eventos, av = agenda.obtener(hoy)
    avisos += av
    texto_agenda = agenda.texto_plantilla(eventos, av)

    # la lista de cumpleaños vive SOLO en Dropbox (el repositorio es público)
    texto_cumples = ""
    if token:
        try:
            datos_c = dropbox.descargar(token, config.DROPBOX_CUMPLES)
            if datos_c is None:
                avisos.append(f"No encuentro {config.DROPBOX_CUMPLES} en la carpeta del pódcast: hoy no hay cumpleaños.")
            else:
                texto_cumples = cumples.texto(cumples.leer(datos_c.decode("utf-8", "replace")), hoy)
        except Exception as e:
            avisos.append(f"Cumpleaños: no se pudo leer la lista ({type(e).__name__})")
    if texto_cumples:
        texto_agenda = texto_cumples + " " + texto_agenda

    # 2) guion
    segs, info = guion.escribir(ahora, datos, resumen_t, texto_agenda)
    avisos += info.get("avisos", [])
    util.log(f"Guion: {info.get('modelo')} · {info.get('palabras')} palabras · {len(segs)} segmentos")

    # 3) voces
    with tempfile.TemporaryDirectory() as tmp:
        audios, indice, motor, av = voces.sintetizar(segs, tmp)
        avisos += av
        util.log(f"Voces: {motor} · {len(audios)} trozos")

        # 4) música (la de Dropbox si la has dejado allí) y montaje
        de_dropbox = {}
        if token:
            try:
                for e in dropbox.listar(token, config.DROPBOX_MUSICA):
                    nombre, ext = os.path.splitext(e.get("name", "").lower())
                    if nombre in montaje.PIEZAS and ext in (".mp3", ".wav", ".m4a", ".aif", ".aiff"):
                        de_dropbox[nombre] = dropbox.descargar(token, e["path_lower"])
            except Exception as e:
                avisos.append(f"Música de Dropbox: {e}"[:300])
        musica = montaje.cargar_musica(de_dropbox)
        wav = os.path.join(tmp, "programa.wav")
        duracion = montaje.montar(segs, audios, indice, musica, wav)
        mp3 = os.path.join(SALIDA, "Noticiario de hoy.mp3")
        titulo = f"Noticiario · {util.fecha_larga(ahora)}"
        montaje.a_mp3(wav, mp3, {"title": titulo, "artist": "Noticiario de Iago", "album": "Noticiario de Iago",
                                 "date": hoy.isoformat(), "comment": f"Voz: {motor} · Guion: {info.get('modelo')}"})
    util.log(f"Programa montado: {duracion / 60:.1f} minutos")

    extra = f" · voz: {motor} · {duracion / 60:.1f} min · generado a las {util.ahora():%H:%M}"
    md = guion.a_markdown(segs, dict(info, avisos=avisos), ahora, extra)
    with open(os.path.join(SALIDA, "Guion de hoy.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(SALIDA, "datos.json"), "w", encoding="utf-8") as f:
        json.dump({"tiempo": resumen_t, "horas": horas, "noticias": datos, "agenda": eventos},
                  f, ensure_ascii=False, indent=1, default=str)

    # 5) a Dropbox
    subido = False
    if token:
        with open(mp3, "rb") as f:
            dropbox.subir(token, config.DROPBOX_MP3, f.read())
        dropbox.subir(token, config.DROPBOX_GUION, md.encode("utf-8"))
        subido = True
        util.log("Subido a Dropbox")

    # OJO: el repositorio es público → aquí solo datos técnicos, nada de agenda, nombres ni noticias
    resumen_github([
        f"## 🎙️ {titulo}",
        f"- Duración: **{duracion / 60:.1f} min** · voz: **{motor}** · guion: **{info.get('modelo')}** · {info.get('palabras')} palabras",
        f"- Tiempo: {fuente_tiempo} · noticias: {len(datos['portada'])}+{len(datos['interes'])}+{len(datos['local'])}",
        f"- Dropbox: {'✅ subido' if subido else '⚠️ NO subido'} · tardó {(time.time() - t0) / 60:.1f} min",
        f"- Avisos: {len(avisos)} (el detalle está al final de «Guion de hoy.md», en tu Dropbox)",
    ])
    if not subido:
        util.log("⚠️ El MP3 no se subió a Dropbox.")
        for a in avisos:
            if a.startswith("Dropbox"):
                util.log(a)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        resumen_github(["## ⚠️ El noticiario de hoy falló", "```", traceback.format_exc()[-3000:], "```"])
        sys.exit(1)
