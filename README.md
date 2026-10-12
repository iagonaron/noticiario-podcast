# Noticiario Podcast

Cada mañana, hacia las 7:20 (hora de Madrid), un robot de GitHub monta un pódcast de 12 a 15
minutos con lo que trae el [noticiario](https://noticiarioiago.netlify.app/) y lo deja en
Dropbox, listo para escuchar en el iPhone: una conversación entre dos presentadores, al estilo
de NotebookLM. Funciona solo, con el ordenador apagado y con servicios gratuitos.

## Qué hace, paso a paso

1. **Noticias**: abre el noticiario publicado en un navegador invisible y se lleva lo que
   ya ha elegido (Portada, De Interés, Local, alertas sanitarias, avisos de AEMET y si jugó
   el Madrid). La pestaña Investigación no se usa.
2. **Tiempo**: misma lógica que la pantalla «Hoy» del noticiario (MeteoGalicia para
   temperatura, cielo, viento y UV; Open-Meteo para la probabilidad de lluvia por horas;
   AEMET para los milímetros).
3. **Lo rápido del día**, con plantillas fijas (la IA no lo toca): cumpleaños (`Cumpleaños.txt`
   en Dropbox), festivos y días señalados (`dias_senalados.txt`, festivos de España, Galicia y
   A Coruña, cambio de hora), agenda de hoy y de mañana y el tiempo en dos frases.
4. **Guion**: Gemini (plan gratuito) escribe la conversación: todas las noticias de cada
   pestaña, explicadas fácil y con desenfado. Sin spoilers del Madrid.
5. **Voces**: Gemini en modo conversación (dos voces en la misma toma). Si Gemini falla, el
   episodio entero se hace con Edge (voces de Microsoft), para que llegue igual.
6. **Montaje**: sintonía de entrada y cierre (de la carpeta `musica` de Dropbox), volumen de
   pódcast y MP3.
7. **Dropbox**: sustituye `Noticiario de hoy.mp3` y `Guion de hoy.md` en la carpeta de la app.

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

- **Música**: deja `intro`, `transicion` y/o `cierre` (.mp3 o .wav) en la carpeta `musica`
  del pódcast en Dropbox. Ahora mismo hay una sintonía de la biblioteca libre Mixkit
  (preparada con el flujo «Preparar música»); no se guarda aquí porque su licencia no
  permite redistribuir las pistas sueltas.
- **Días señalados**: edita `dias_senalados.txt` (y los festivos locales, en `podcast/festivos.py`).
- **Cumpleaños**: edita `Cumpleaños.txt` en la carpeta del pódcast en Dropbox.
- **Voces**: en Settings → Secrets and variables → Actions → *Variables*, crea `VOZ_A` /
  `VOZ_B` con el nombre de una voz de Gemini (ahora Kore y Puck; otras: Aoede, Leda,
  Charon, Orus, Achird, Sulafat) o `MOTOR_VOZ` = `edge` para usar solo las voces de Microsoft.

## Pausar, probar o deshacer

- **Probar ahora**: pestaña Actions → «Noticiario Podcast» → *Run workflow*.
- **Comprobar un episodio**: Actions → «Comprobar episodio» → *Run workflow* (lo transcribe y
  deja «Comprobación.txt» en Dropbox).
- **Pausar**: Actions → «Noticiario Podcast» → `···` → *Disable workflow*.
- **Quitarlo del todo**: borrar este repositorio y, en Dropbox, la app «Noticiario Podcast»
  (dropbox.com/account/connected_apps). Nada más depende de él.
