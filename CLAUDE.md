# Notas para Claude (este repositorio es público: aquí nada personal)

- El episodio diario lo arranca a las 7:16 de Madrid la tarea programada de Claude «Despertador
  del Noticiario Podcast» (Run workflow con `forzar` = `no`); las citas de GitHub son solo respaldo.
- Cupo gratuito de Gemini: se renueva a medianoche de California (9:00 en Madrid). Cada modelo de
  voz admite 10 peticiones al día y un episodio gasta 4. Cualquier prueba con voces reales hecha
  después de las 9:00 sale del cupo del episodio de la mañana siguiente: el 14-oct-2026 una voz
  salió entera del modelo «lite» por las pruebas del día anterior.
  - Prueba siempre con `prueba` = `si` (ya evita los modelos principales de voz y de texto) y, si no
    hace falta oír la voz de Gemini, con `modelos_voz` = `piper:local`.
  - Como mucho una prueba al día con el modelo de voz principal, y solo si hace falta de verdad.
  - Los modos del flujo «Diagnóstico» que generan voz (voz, vozlarga, cortes) también gastan cupo.
  - El texto también tiene cupo: «Preparar música» → `describir` y las pruebas completas usan
    gemini-3.6-flash (reserva del guion). El 16-oct quedó agotado tras describir 20 pistas: mejor
    pocas pistas, o antes de las 9:00.
- Voces: Lucía = Kore, Martín = Algieba (la eligió Iago el 15-oct-2026 entre voces graves; antes Puck).
- Pronunciación (17-oct-2026): las voces leían «Xunta» como «Yunta». `pronuncia.para_voz` les escribe la
  x gallega como «sh» (Xunta → Shunta, Arteixo → Arteisho, Sanxenxo → Sanshensho; lista fija + reglas que
  no tocan taxi, México, xilófono…); el guion escrito no cambia y `alinear.norma` cuenta «sh» = «x».
  Prueba de oído: Diagnóstico `pronuncia` (1 petición por voz) → Dropbox /Pruebas/Pronunciación/.
- Cortes: cada lote de voz se guarda tal cual en Dropbox (/Pruebas/Crudo del episodio, o «Crudo de la
  prueba»), con sus textos y cortes. Si Iago oye un corte mal hecho, el flujo «Diagnóstico» con
  `pruebas` = `recortar` (y `crudo` = esa carpeta) vuelve a cortar esos lotes sin gastar cupo y deja el
  detalle en /Pruebas/Recorte - informe.txt; `cortes_viejos` = `si` compara con la regla anterior.
- Pausas de Martín (17-oct-2026): Algieba deja a veces silencios de 8 a 18 s entre frases (diagnóstico
  `pausas`, sin cupo). Antes eso hacía rechazar el lote por «turno demasiado largo» y pedirlo otra vez:
  el 17-oct su voz gastó 6 peticiones y el episodio 8 de 10. Ahora las comprobaciones de duración
  (`alinear.cortes` y `voces._razonable`) no cuentan los silencios hondos (≥40 dB bajo la voz), que el
  montaje quita igual (`alinear._hablado`). Los lotes rechazados también se guardan en el crudo
  («rechazado»: motivo), para estudiarlos con `recortar` o `pausas`.
- Bordes de cada frase (16-oct-2026): lo que suena antes de la primera palabra o después de la
  última sin ser del guion (sílaba suelta, respiración, etiqueta a medio leer), corto y separado por
  un silencio, se quita (`alinear._limpiar`). El resumen de cada lote dice cuántos «bordes limpiados».
- Deriva de voz: `huella.py` compara el timbre de cada frase con el resto de la misma voz; si varias
  seguidas se alejan, `voces._corregir_derivas` las rehace (1 petición, máx. 2 tramos por voz). El
  diagnóstico `timbre` aplica la misma regla al crudo guardado. Umbrales aún sin calibrar con un caso
  real localizado (el 16-oct Iago oyó un cambio de voz de Lucía que la huella no destacó).
- Local (16-oct-2026, tras perderse un terremoto que se notó en media Galicia): además de las locales del
  noticiario (sobre todo de Coruña), `noticias.galicia()` agrupa lo que cuentan los medios de Galicia en
  24 h (Google Noticias «Galicia when:1d» + sección Galicia de La Voz) y lo ordena por cuántos medios lo
  cuentan. El guionista elige 3 locales por importancia; si algo de Galicia lo cuentan 6 medios o más,
  va siempre y la primera (cuarta noticia). Candidatas de cada día: /Pruebas/Noticias candidatas.json.
  Diagnósticos: `galicia`, `fuentes_galicia`, `estado` (qué guarda el noticiario por dentro).
- Tiempo (21-oct-2026): el cielo sale de MeteoGalicia y la probabilidad por horas de Open-Meteo, que a veces
  no coinciden; si MeteoGalicia pone chubascos o lluvia en alguna hora, `tiempo.texto_breve` dice como poco
  «puede caer algo» (salió «…con algún episodio de chubascos… No va a llover»). Diagnóstico `tiempo` (sin cupo).
- Distinto Básico (21-oct-2026, tras quedarse el 20-oct sin momento): con Gemini saturado, 3.8 y 3.6 tardan
  hasta 4 min en decir 503. `planes.proponer` pide tres opciones por petición y se queda la primera válida;
  si un modelo no contesta en 100 s lanza también el siguiente (relevo, dos vueltas, límite 525 s desde el
  arranque); la siguiente petición sabe qué opciones salieron repetidas; se descarta lo propuesto sin leer
  ninguna agenda (3-flash-preview lo hacía). Si no hay plan nuevo, se recuerda uno de otro día que siga en pie
  (`planes.recordatorio`, desde /Distinto Básico - propuestas.json). Diagnósticos: `planes`, `planes_tiempos`
  (`modelos_texto`), `historia` (Diagnóstico y guion de otro día, desde el historial de Dropbox; `fecha`).
- Emojis (21-oct-2026): `util.sin_emojis` deja un espacio en su sitio y lee las flechas como «a».
- Horas (21-oct-2026, lo pidió Iago): en los títulos de la agenda, «9.3013.30» → «9:30 a 13:30» y
  «Ferrer1430» → «Ferrer 14:30» (`agenda._horas`; así los escribe él en el calendario), y la voz dice toda
  hora «13:30» con números, tal cual: «trece treinta», «catorce en punto» (`pronuncia.para_voz`), para no
  dudar de qué hora es. Las horas de los eventos siguen «a las nueve de la noche». Ver los títulos tal cual
  y cómo se leen: diagnóstico `agenda_caracteres` (a Dropbox /Pruebas, privado).
- Depor en Riazor (28-oct-2026): esos eventos del calendario (los apunta la tarea de los lunes) solo se dicen
  el mismo día, no en «Y mañana…» (`agenda.SOLO_EL_DIA`); al Iago solo le importan ese día, para aparcar.
- Música: el flujo «Preparar música» (modos listar, describir, muestras, fondo) prepara candidatas;
  `muestras` monta un trozo de programa real con cada una en Dropbox /Pruebas/Músicas para elegir/.
  Antes de `fondo`, guarda una copia de /musica/fondo.mp3 (se sobrescribe).
- Desde esta sesión GraphQL no funciona: usa `gh api` (REST). Los registros de las ejecuciones no se
  pueden descargar; lo útil está en las anotaciones del trabajo
  (`gh api repos/iagonaron/noticiario-podcast/check-runs/<job_id>/annotations`) y en
  «Diagnóstico.txt» de la carpeta del pódcast en Dropbox.
- Gimnasio (28-oct-2026): bloque opcional «Gimnasio» después de la agenda (`gimnasio.py`, plantilla fija, sin IA)
  (en el pódcast SOLO «a tu hora / antes / más tarde, a las X»; la frase con el motivo, la gente y la bici, y la
  tabla, van a Dropbox /Gimnasio hoy.md para el correo de las 7:42 «Ocupación GYM y repositorios»; los días con HIIT —el siguiente al último
  entreno de su app, leída de Supabase con las claves de /Gimnasio.txt— también si tendrá la bici de spinning) y una tabla por franjas al final del guion escrito. Todo lo personal (la web de reservas, las horas de Iago,
  qué actividades le molestan) vive SOLO en Dropbox /Gimnasio.txt; sin ese fichero no hay bloque. La web marca
  plazas libres (personas = aforo − libres; aforo = lo más alto de esa franja en esta semana y la siguiente).
  Diagnóstico `gimnasio` (sin cupo) → Dropbox /Pruebas/Gimnasio (prueba).md.
