# Noticiario Podcast

Cada mañana, hacia las 7:20 (hora de Madrid), un robot de GitHub monta un pódcast de unos
11 minutos con lo que trae el [noticiario](https://noticiarioiago.netlify.app/) y lo deja
en Dropbox, listo para escuchar en el iPhone. Funciona solo, con el ordenador apagado y
con servicios gratuitos.

## Qué hace, paso a paso

1. **Noticias**: abre el noticiario publicado en un navegador invisible y se lleva lo que
   ya ha elegido (Portada, De Interés, Local, alertas sanitarias, avisos de AEMET y si jugó
   el Madrid). La pestaña Investigación no se usa.
2. **Tiempo**: misma lógica que la pantalla «Hoy» del noticiario (MeteoGalicia para
   temperatura, cielo, viento y UV; Open-Meteo para la probabilidad de lluvia por horas;
   AEMET para los milímetros).
3. **Agenda y cumpleaños**: de las direcciones iCal secretas y de `Cumpleaños.txt` en la
   carpeta del pódcast en Dropbox. Se leen con plantilla fija: la IA no las toca.
4. **Guion**: lo escribe Gemini (plan gratuito). Si cuela en el tiempo alguna cifra que no
   está en los datos, ese bloque se sustituye por la plantilla. Sin spoilers del Madrid.
5. **Voces**: dos locutores que se turnan por bloques, con Gemini. Si Gemini falla, el
   episodio entero se hace con Edge (voces de Microsoft), para que llegue igual.
6. **Montaje**: sintonía, transiciones, música bajo el tiempo, volumen de pódcast y MP3.
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

- **Música**: deja `intro`, `transicion`, `fondo` y/o `cierre` (.mp3 o .wav) en la carpeta
  `musica` del pódcast en Dropbox. Si no están, se usan las de este repositorio
  (`musica/componer.py` las genera).
- **Cumpleaños**: edita `Cumpleaños.txt` en la carpeta del pódcast en Dropbox.
- **Voces**: en Settings → Secrets and variables → Actions → *Variables*, crea `VOZ_A` /
  `VOZ_B` con el nombre de una voz de Gemini (por ejemplo Kore, Aoede, Leda, Charon,
  Orus, Iapetus) o `MOTOR_VOZ` = `edge` para usar solo las voces de Microsoft.

## Pausar, probar o deshacer

- **Probar ahora**: pestaña Actions → «Noticiario Podcast» → *Run workflow*.
- **Pausar**: Actions → «Noticiario Podcast» → `···` → *Disable workflow*.
- **Quitarlo del todo**: borrar este repositorio y, en Dropbox, la app «Noticiario Podcast»
  (dropbox.com/account/connected_apps). Nada más depende de él.
