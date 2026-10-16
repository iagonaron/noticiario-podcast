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
- Voces: Lucía = Kore, Martín = Algieba (la eligió Iago el 15-oct-2026 entre voces graves; antes Puck).
- Cortes: cada lote de voz se guarda tal cual en Dropbox (/Pruebas/Crudo del episodio, o «Crudo de la
  prueba»), con sus textos y cortes. Si Iago oye un corte mal hecho, el flujo «Diagnóstico» con
  `pruebas` = `recortar` (y `crudo` = esa carpeta) vuelve a cortar esos lotes sin gastar cupo y deja el
  detalle en /Pruebas/Recorte - informe.txt; `cortes_viejos` = `si` compara con la regla anterior.
- Bordes de cada frase (16-oct-2026): lo que suena antes de la primera palabra o después de la
  última sin ser del guion (sílaba suelta, respiración, etiqueta a medio leer), corto y separado por
  un silencio, se quita (`alinear._limpiar`). El resumen de cada lote dice cuántos «bordes limpiados».
- Deriva de voz: `huella.py` compara el timbre de cada frase con el resto de la misma voz; si varias
  seguidas se alejan, `voces._corregir_derivas` las rehace (1 petición, máx. 2 tramos por voz). El
  diagnóstico `timbre` aplica la misma regla al crudo guardado. Umbrales aún sin calibrar con un caso
  real localizado (el 16-oct Iago oyó un cambio de voz de Lucía que la huella no destacó).
- Música: el flujo «Preparar música» (modos listar, describir, muestras, fondo) prepara candidatas;
  `muestras` monta un trozo de programa real con cada una en Dropbox /Pruebas/Músicas para elegir/.
  Antes de `fondo`, guarda una copia de /musica/fondo.mp3 (se sobrescribe).
- Desde esta sesión GraphQL no funciona: usa `gh api` (REST). Los registros de las ejecuciones no se
  pueden descargar; lo útil está en las anotaciones del trabajo
  (`gh api repos/iagonaron/noticiario-podcast/check-runs/<job_id>/annotations`) y en
  «Diagnóstico.txt» de la carpeta del pódcast en Dropbox.
