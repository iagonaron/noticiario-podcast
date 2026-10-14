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
- Desde esta sesión GraphQL no funciona: usa `gh api` (REST). Los registros de las ejecuciones no se
  pueden descargar; lo útil está en las anotaciones del trabajo
  (`gh api repos/iagonaron/noticiario-podcast/check-runs/<job_id>/annotations`) y en
  «Diagnóstico.txt» de la carpeta del pódcast en Dropbox.
