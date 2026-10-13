# Noticiario Podcast

Cada mañana, hacia las 7:20 (hora de Madrid), un robot de GitHub monta un pódcast de unos 12
minutos con lo que trae el [noticiario](https://noticiarioiago.netlify.app/), más un plan del
«Distinto Básico» al final, y lo deja en Dropbox, listo para escuchar en el iPhone: un diálogo
entre dos voces, con música de informativo. Funciona solo, con el ordenador apagado y con
servicios gratuitos.

## Qué hace, paso a paso

1. **Noticias**: abre el noticiario publicado en un navegador invisible y se lleva lo que
   ya ha elegido (Exprés de El País, De Interés, Local y alertas sanitarias). El Exprés se baja
   antes por varios caminos (proxy de Netlify, directo, allorigins o una pestaña de navegador),
   porque El País bloquea a ratos unos u otros desde los servidores de GitHub.
2. **Tiempo**: misma lógica que la pantalla «Hoy» del noticiario (MeteoGalicia, Open-Meteo y AEMET).
3. **Lo rápido**, con plantillas fijas (la IA no lo toca): «Hoy es…», cumpleaños
   (`Cumpleaños.txt` en Dropbox), festivos y días señalados (`dias_senalados.txt`, festivos de
   España, Galicia y A Coruña, cambio de hora), agenda de hoy y de mañana y el tiempo en dos frases.
4. **Guion**: Gemini (plan gratuito) escribe un diálogo ágil entre dos voces, sin saludos ni
   nombres: titulares → Coruña y Galicia (3) → ciencia, salud y economía, en unos 12 minutos
   (cada noticia, 2 a 4 turnos cortos). Sin spoilers de deportes.
5. **Momento Distinto Básico** (después de los 12 minutos, como extra): mientras se hace lo demás,
   Gemini lee las agendas de A Coruña (Concello, Quincemil, La Ganzúa, Planomato) y propone un plan
   con los criterios de `Distinto Básico.txt` (en Dropbox). Lo propuesto se apunta en
   `Distinto Básico - propuestas.txt` para no repetir.
6. **Voces**: cada voz se genera aparte y siempre con el mismo modelo de Gemini de principio a fin
   (así no cambia de timbre), en lotes de turnos con una pausa larga entre turno y turno. Luego se
   cortan turno a turno con una transcripción automática (faster-whisper) y se intercalan.
   Hay cuatro modelos de voz en cadena; si ninguno puede, Edge o Piper (sin conexión).
7. **Montaje** de informativo: la música (`musica/fondo.mp3` en Dropbox) suena arriba al empezar,
   baja cuando hablan, sube 2-3 segundos entre noticias y cierra arriba. Volumen de pódcast y MP3.
8. **Dropbox**: sustituye `Noticiario de hoy.mp3` y `Guion de hoy.md` en la carpeta de la app.

## Lo privado no está aquí

Este repositorio es público. Las claves, las direcciones de los calendarios y la lista de
cumpleaños **no** están en él: viven en los secretos de GitHub (que nadie puede leer) y en
la carpeta del pódcast en Dropbox. El permiso de Dropbox se guarda cifrado con la App secret.
Los registros de GitHub solo muestran datos técnicos.

| Secreto (Settings → Secrets and variables → Actions) | Qué es |
|---|---|
| `GEMINI_API_KEY` | Clave gratuita de Google AI Studio (proyecto sin facturación) |
| `DROPBOX_APP_KEY` / `DROPBOX_APP_SECRET` | La app de Dropbox «Noticiario Podcast» (carpeta de app) |
| `CALENDARIOS_ICS` | Direcciones iCal secretas, una por línea |

## Cambiar cosas sin tocar código

- **Música**: la cama musical es `musica/fondo.mp3` en la carpeta del pódcast en Dropbox (una
  pista de informativo de la biblioteca libre Mixkit, preparada con el flujo «Preparar música»,
  que también sabe listar, analizar y «escuchar» pistas candidatas). No se guarda aquí porque su
  licencia no permite redistribuir las pistas sueltas.
- **Distinto Básico**: edita `Distinto Básico.txt` en la carpeta del pódcast en Dropbox.
- **Días señalados**: edita `dias_senalados.txt` (y los festivos locales, en `podcast/festivos.py`).
- **Cumpleaños**: edita `Cumpleaños.txt` en la carpeta del pódcast en Dropbox.
- **Voces**: en Settings → Secrets and variables → Actions → *Variables*, crea `VOZ_A` /
  `VOZ_B` con el nombre de una voz de Gemini (ahora Kore y Puck; otras: Aoede, Leda,
  Charon, Orus, Achird, Sulafat) o `MOTOR_VOZ` = `edge` para usar solo las voces de Microsoft.

## Pausar, probar o deshacer

- **Probar ahora**: pestaña Actions → «Noticiario Podcast» → *Run workflow*.
- **Comprobar un episodio**: Actions → «Comprobar episodio» → *Run workflow* (lo transcribe y
  deja «Comprobación.txt» en Dropbox).
- **Qué pasó en cada ejecución**: «Diagnóstico.txt» en la carpeta del pódcast en Dropbox (fuentes,
  tiempos, modelos de voz usados y avisos).
- **Pausar**: Actions → «Noticiario Podcast» → `···` → *Disable workflow*.
- **Quitarlo del todo**: borrar este repositorio y, en Dropbox, la app «Noticiario Podcast»
  (dropbox.com/account/connected_apps). Nada más depende de él.
