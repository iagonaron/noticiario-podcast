"""Cómo tienen que sonar algunas palabras. Solo cambia el texto que se manda a las voces: el guion
escrito (el que va a Dropbox) se queda tal cual.

La x gallega suena «sh» (Xunta = «Shunta»), pero las voces de Gemini la leían a la castellana
(«Yunta», «Arteikso»), así que a las voces se les escribe como suena. Reglas, de la más segura a
la menos:
1. PALABRAS: una lista fija, para las que no siguen ninguna regla (Muxía, Laxe, Xurxo…) y para
   las pocas x de fuera de Galicia que suenan de otra forma (Ximo Puig = «Chimo»).
2. Nombre propio que empieza por X y vocal (Xunta, Xacobeo, Xosé, Xinzo, Xove, Xabi, Xi Jinping…),
   salvo las palabras castellanas que empiezan así (xenofobia, xilófono…), que suenan «s».
3. x detrás de una i de diptongo (Arteixo, Teixeiro, Meixoeiro, Boqueixón, Caixa, Aleix…) o
   detrás de n (Sanxenxo, Rianxo, Anxo, Conxo, lonxa): en castellano no hay palabras así.
Lo que no entra en ninguna (taxi, examen, México, Texas, Xbox, la red social X…) no se toca.

Para cortar las frases (alinear.py) da igual cómo se escribiera: allí «sh» y «x» cuentan igual.
"""
import re

_VOCAL = "aeiouáéíóúü"

PALABRAS = {
    # gallegas (y alguna asturiana) con x que las reglas de abajo no cubren
    "xurxo": "shursho", "uxía": "ushía", "uxío": "ushío", "muxía": "mushía", "laxe": "lashe",
    "pasaxe": "pasashe", "igrexa": "igresha", "irixoa": "irishoa", "irixo": "irisho",
    "vilaxoán": "vilashoán", "xuxán": "shushán", "dexo": "desho", "coruxo": "corusho",
    "xixón": "shishón",
    # x que no suena «sh»
    "ximena": "jimena", "xerez": "jerez", "ximo": "chimo", "xàtiva": "chátiva", "xàbia": "chábia",
}
# palabras castellanas que empiezan por x + vocal (suenan «s»): xenofobia, xenón, xerografía, xilófono…
CASTELLANAS = ("xeno", "xenó", "xero", "xeró", "xil", "xíl")

_RE_PALABRAS = re.compile(r"\b(" + "|".join(sorted(map(re.escape, PALABRAS), key=len, reverse=True)) + r")\b",
                          re.IGNORECASE)
_RE_INICIAL = re.compile(rf"\bX(?=[{_VOCAL}])\w*")                       # Xunta, Xosé (no XIX ni Xbox)
_RE_DIPTONGO = re.compile(rf"(?<=[aeouáéóú]i)x(?=[{_VOCAL}]|\b)", re.IGNORECASE)   # Arteixo, Aleix
_RE_NX = re.compile(rf"(?<=n)x(?=[{_VOCAL}])", re.IGNORECASE)            # Sanxenxo, Rianxo


def _mismo_caso(original, nuevo):
    if original.isupper() and len(original) > 1:
        return nuevo.upper()
    return nuevo[0].upper() + nuevo[1:] if original[:1].isupper() else nuevo


def _sh(m):
    return "SH" if m.group(0).isupper() else "sh"


def _inicial(m):
    palabra = m.group(0)
    return palabra if palabra.lower().startswith(CASTELLANAS) else "Sh" + palabra[1:]


# ---------------------------------------------------------------- horas
# «13:30» se dice «trece treinta», con números tal cual, y «14:00», «catorce en punto»: Iago lo prefiere así
# (21-oct-2026) a «la una y media», para no tener dudas de qué hora es. Las horas de la agenda llegan ya
# como «9:30» (agenda._horas).
_UNIDADES = ("cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciséis "
             "diecisiete dieciocho diecinueve veinte veintiuno veintidós veintitrés veinticuatro veinticinco "
             "veintiséis veintisiete veintiocho veintinueve").split()
_DECENAS = {3: "treinta", 4: "cuarenta", 5: "cincuenta"}
_RE_HORA = re.compile(r"(?<![\d:.,])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])")


def _numero(n, femenino=False):
    texto = _UNIDADES[n] if n < 30 else _DECENAS[n // 10] + ("" if n % 10 == 0 else " y " + _UNIDADES[n % 10])
    return re.sub(r"uno$", "una", texto) if femenino else texto      # la una, las veintiuna


def _hora(m):
    h, mm = int(m.group(1)), int(m.group(2))
    if mm == 0:
        return f"{_numero(h, True)} en punto"
    return f"{_numero(h, True)} {'cero ' if mm < 10 else ''}{_numero(mm)}"


def _aplicar(texto):
    """(texto para la voz, cuántos cambios)."""
    if not texto:
        return texto, 0
    t, n = texto, 0
    if re.search("[xX]", t):
        for rx, cambio in ((_RE_PALABRAS, lambda m: _mismo_caso(m.group(0), PALABRAS[m.group(0).lower()])),
                           (_RE_INICIAL, _inicial), (_RE_DIPTONGO, _sh), (_RE_NX, _sh)):
            t, k = rx.subn(cambio, t)
            n += k
    if ":" in t:
        t, k = _RE_HORA.subn(_hora, t)
        n += k
    return t, n


def para_voz(texto):
    """El texto tal como lo tienen que leer las voces («La Xunta» → «La Shunta», «13:30» → «trece treinta»)."""
    return _aplicar(texto)[0]


def cuantas(texto):
    """Cuántas palabras u horas cambia para_voz."""
    return _aplicar(texto)[1]
