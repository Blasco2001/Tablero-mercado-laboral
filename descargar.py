#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Descarga los anexos de la GEIH desde el portal del DANE.
========================================================

Es el eslabon que faltaba para que el tablero se actualice solo. Antes de
esto alguien tenia que acordarse de bajar cuatro .xlsx cada mes; si esa
persona salia de vacaciones, el tablero se congelaba.

Uso:
    python descargar.py                # busca el mes mas reciente publicado
    python descargar.py --mes jun2026  # fuerza un mes concreto
    python descargar.py --simular      # dice que haria, sin escribir nada

Codigos de salida -- el workflow los interpreta, no son adorno:

    0   hay anexos nuevos en datos/. Sigue el ETL.
    2   no hay nada que hacer: el DANE todavia no publica, o ya estamos al
        dia. NO es un error y NO debe abrir un issue ni publicar nada.
    1   error de verdad (un archivo corrupto, un disco lleno). Que se entere
        alguien.

La regla que manda: ante la duda, no publicar. Es preferible que el sitio
muestre las cifras del mes pasado a que muestre cifras equivocadas con el
logo de la Camara encima.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import ssl
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DESTINO = RAIZ / "datos"
HISTORIAL = "historial.csv"   # vive junto a los anexos, sea cual sea el destino

BASE = "https://www.dane.gov.co"
ARCHIVOS = f"{BASE}/files/operaciones/GEIH"
PORTAL = f"{BASE}/index.php/estadisticas-por-tema/mercado-laboral"

MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]

# El DANE no usa un solo patron. El anexo general se nombra por el mes de
# cierre del trimestre movil; los otros tres nombran el trimestre completo.
# Y ademas cambian de forma cuando el trimestre cruza el fin de anio:
#
#     anex-GEIH-jun2026.xlsx              general, mes de cierre
#     anex-GEIHEISS-abr-jun2026.xlsx      trimestre dentro del mismo anio
#     anex-GEIHEISS-dic2025-feb2026.xlsx  trimestre a caballo entre dos anios
#
# Las tres formas estan comprobadas contra el portal. La ultima es la que
# rompe cualquier patron ingenuo: 'dic-feb2026' da 404.
MODULOS = {
    "general": {
        "prefijo": "anex-GEIH-",
        "cadencia": "mes",
        "pagina": f"{PORTAL}/empleo-y-desempleo",
    },
    "informalidad": {
        "prefijo": "anex-GEIHEISS-",
        "cadencia": "trimestre",
        "pagina": f"{PORTAL}/empleo-informal-y-seguridad-social",
    },
    "sexo": {
        "prefijo": "anex-GEIHMLS-",
        "cadencia": "trimestre",
        "pagina": f"{PORTAL}/segun-sexo",
    },
    "juventud": {
        "prefijo": "anex-GEIHMLJ-",
        "cadencia": "trimestre",
        "pagina": f"{PORTAL}/mercado-laboral-de-la-juventud",
    },
}

AGENTE = ("Mozilla/5.0 (compatible; ObservatorioMercadoLaboral-CCC/1.0; "
          "+https://www.ccc.org.co)")
ESPERA = 30

# Un trimestre movil termina como muy pronto un mes despues de medirse, y el
# DANE se toma otro mes en publicarlo. Seis meses hacia atras cubre de sobra
# cualquier retraso razonable sin ponerse a rastrear el portal entero.
MESES_ATRAS = 6


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def norm(txt: str) -> str:
    """Minusculas, sin tildes, sin guiones ni espacios ni parentesis.

    Sirve para que 'anex-GEIH-jun2026.xlsx' (como lo sirve el DANE) y
    'anexGEIHjun2026 (2).xlsx' (como lo guarda el navegador) se comparen
    igual. Es la misma normalizacion que usa localizar_anexos() en etl.py.
    """
    t = unicodedata.normalize("NFKD", str(txt).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[\s\-_()]+", "", t)


RE_PERIODO = re.compile("(" + "|".join(MESES) + r")(\d{4})")


def cierre_de(nombre: str) -> tuple[int, int] | None:
    """(anio, mes) de cierre que declara el nombre de un archivo.

    Se toma la ULTIMA pareja mes+anio del nombre, que es siempre el cierre:
    'abrjun2026' cierra en junio, 'dic2025ene2026' cierra en enero. Tambien
    aguanta la basura que agrega el navegador ('..._2.xlsx').
    """
    hallazgos = RE_PERIODO.findall(norm(nombre))
    if not hallazgos:
        return None
    mes, anio = hallazgos[-1]
    return int(anio), MESES.index(mes) + 1


def mes_menos(anio: int, mes: int, n: int) -> tuple[int, int]:
    """Retrocede n meses sobre (anio, mes), con mes de 1 a 12."""
    total = anio * 12 + (mes - 1) - n
    return total // 12, total % 12 + 1


def nombre_esperado(modulo: str, anio: int, mes: int) -> str:
    """Nombre del archivo del DANE para el trimestre que cierra en (anio, mes)."""
    cfg = MODULOS[modulo]
    if cfg["cadencia"] == "mes":
        return f"{cfg['prefijo']}{MESES[mes - 1]}{anio}.xlsx"

    # El trimestre movil abarca los tres meses que terminan en (anio, mes)
    a1, m1 = mes_menos(anio, mes, 2)
    if a1 == anio:
        cola = f"{MESES[m1 - 1]}-{MESES[mes - 1]}{anio}"
    else:
        # Cruza el fin de anio: cada extremo carga el suyo
        cola = f"{MESES[m1 - 1]}{a1}-{MESES[mes - 1]}{anio}"
    return f"{cfg['prefijo']}{cola}.xlsx"


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Red
# ---------------------------------------------------------------------------

def contexto_ssl() -> ssl.SSLContext:
    """Contexto TLS con una autoridad certificadora que si exista.

    En Linux -- que es donde corre el workflow -- el almacen del sistema
    alcanza y esto no hace nada. En algunos Python de macOS no queda ninguno
    configurado (ssl.get_default_verify_paths().cafile es None) y entonces
    TODA descarga falla con 'self-signed certificate in certificate chain',
    que despista porque el certificado del DANE es perfectamente valido.

    Se usa certifi solo en ese caso, y solo si esta instalado. No se apaga
    nunca la verificacion: da lo mismo que sean cifras publicas, bajarlas sin
    verificar el certificado seria confiar en cualquiera que se meta en medio.
    """
    if ssl.get_default_verify_paths().cafile:
        return ssl.create_default_context()
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


CONTEXTO = contexto_ssl()


def pedir(url: str, solo_cabecera: bool = False) -> bytes | None:
    """Trae una URL. Devuelve None si no esta (404) o si la red falla.

    Que un fallo de red devuelva None y no una excepcion es deliberado: un
    cron diario contra un portal publico se va a topar con cortes, y un corte
    no es motivo para despertar a nadie. Manana lo vuelve a intentar.
    """
    pet = urllib.request.Request(
        url, headers={"User-Agent": AGENTE},
        method="HEAD" if solo_cabecera else "GET")
    try:
        with urllib.request.urlopen(pet, timeout=ESPERA, context=CONTEXTO) as r:
            return b"" if solo_cabecera else r.read()
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"    [aviso] {e.code} en {url}")
        return None
    except Exception as e:
        print(f"    [aviso] no se pudo consultar {url}: {e}")
        return None


def buscar_en_portal(modulo: str) -> dict[tuple[int, int], str]:
    """Respaldo: lee la pagina del modulo y saca los enlaces .xlsx que sirven.

    El patron de URL lleva estable desde abril de 2023, pero antes de esa
    fecha los anexos vivian en otra ruta y con otro nombre. Ese antecedente
    es justamente la razon de no confiar solo en el patron.

    El filtro por prefijo exacto importa: en la misma pagina cuelgan el anexo
    desestacionalizado, los de RELAB y el de economia creativa, que este
    tablero no usa.
    """
    html = pedir(MODULOS[modulo]["pagina"])
    if html is None:
        return {}
    texto = html.decode("utf-8", "replace")
    patron = re.compile(
        re.escape(MODULOS[modulo]["prefijo"])
        + r"((?:" + "|".join(MESES) + r")[0-9\-]*?\d{4})\.xlsx", re.I)

    encontrados: dict[tuple[int, int], str] = {}
    for href in re.findall(r'href="([^"]+\.xlsx)"', texto, re.I):
        archivo = href.rsplit("/", 1)[-1]
        if not patron.fullmatch(archivo):
            continue
        cierre = cierre_de(archivo)
        if cierre:
            encontrados[cierre] = href if href.startswith("http") else BASE + href
    return encontrados


def resolver(modulo: str, anio: int, mes: int) -> str | None:
    """URL del anexo del modulo para ese cierre, o None si no existe todavia.

    Primero la URL predecible, que es un HEAD y cuesta nada. Si da 404, se
    lee la pagina del DANE por si cambiaron el nombre.
    """
    directa = f"{ARCHIVOS}/{nombre_esperado(modulo, anio, mes)}"
    if pedir(directa, solo_cabecera=True) is not None:
        return directa
    return buscar_en_portal(modulo).get((anio, mes))


# ---------------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------------

def es_xlsx(ruta: Path) -> bool:
    """Un .xlsx es un ZIP con un workbook adentro.

    Cuando el portal esta en mantenimiento devuelve una pagina de error con
    codigo 200 y extension .xlsx. Sin esta comprobacion, esa pagina entraria
    a datos/ y el ETL reventaria mucho mas adelante, con un mensaje que no
    dice nada sobre lo que de verdad paso.
    """
    try:
        with zipfile.ZipFile(ruta) as z:
            return any(n.startswith("xl/") for n in z.namelist())
    except Exception:
        return False


def ultimo_publicado(hasta: tuple[int, int], meses: int
                     ) -> tuple[tuple[int, int], dict[str, str]] | None:
    """El cierre mas reciente en que estan disponibles LOS CUATRO modulos.

    Tienen que ser los cuatro y del mismo mes. El modulo general fija la
    grilla de periodos del ETL; sexo y juventud se leen sin realinear. Si uno
    llega un mes tarde, sus series quedan mas cortas que la grilla y
    verificar.py lo tumba. Antes que provocar esa falsa alarma cada mes, se
    espera a que el DANE los tenga todos.
    """
    anio, mes = hasta
    for atras in range(meses):
        a, m = mes_menos(anio, mes, atras)
        urls = {}
        for modulo in MODULOS:
            url = resolver(modulo, a, m)
            if url is None:
                break
            urls[modulo] = url
        else:
            return (a, m), urls
        if urls:
            print(f"  {MESES[m - 1]}{a}: solo {len(urls)} de 4 modulos; "
                  f"el DANE todavia no los publica juntos")
    return None


# ---------------------------------------------------------------------------
# Autoprueba
# ---------------------------------------------------------------------------

# Nombres verificados uno por uno contra el portal del DANE. Los tres ultimos
# son los que cruzan el fin de anio, que es donde se rompe cualquier patron
# ingenuo: 'dic-feb2026' devuelve 404, tiene que ser 'dic2025-feb2026'.
CASOS = [
    ("general",      2026, 6, "anex-GEIH-jun2026.xlsx"),
    ("general",      2025, 12, "anex-GEIH-dic2025.xlsx"),
    ("general",      2026, 1, "anex-GEIH-ene2026.xlsx"),
    ("informalidad", 2026, 6, "anex-GEIHEISS-abr-jun2026.xlsx"),
    ("informalidad", 2026, 5, "anex-GEIHEISS-mar-may2026.xlsx"),
    ("informalidad", 2026, 3, "anex-GEIHEISS-ene-mar2026.xlsx"),
    ("informalidad", 2025, 12, "anex-GEIHEISS-oct-dic2025.xlsx"),
    ("sexo",         2026, 6, "anex-GEIHMLS-abr-jun2026.xlsx"),
    ("juventud",     2026, 6, "anex-GEIHMLJ-abr-jun2026.xlsx"),
    # --- frontera de anio ---
    ("informalidad", 2026, 1, "anex-GEIHEISS-nov2025-ene2026.xlsx"),
    ("informalidad", 2026, 2, "anex-GEIHEISS-dic2025-feb2026.xlsx"),
    ("juventud",     2026, 2, "anex-GEIHMLJ-dic2025-feb2026.xlsx"),
]

# El cierre que declara cada nombre. Mezcla los nombres del DANE con los que
# deja el navegador al descargar dos veces el mismo archivo.
CIERRES = [
    ("anex-GEIH-jun2026.xlsx", (2026, 6)),
    ("anexGEIHjun2026_2.xlsx", (2026, 6)),
    ("anexGEIHMLJabrjun2026_1.xlsx", (2026, 6)),
    ("anexGEIHEISSabrjun2026.xlsx", (2026, 6)),
    ("anex-GEIHEISS-nov2025-ene2026.xlsx", (2026, 1)),
    ("anex-GEIHEISS-dic2025-feb2026.xlsx", (2026, 2)),
    ("anexGEIHMLSabrjun2026 (1).xlsx", (2026, 6)),
]


def autoprueba() -> int:
    """Comprueba la logica de nombres sin tocar la red."""
    fallos = []

    print("\nNombres que se le piden al DANE")
    for modulo, anio, mes, esperado in CASOS:
        obtenido = nombre_esperado(modulo, anio, mes)
        if obtenido == esperado:
            print(f"  ok    {modulo:13s} {MESES[mes-1]}{anio} -> {esperado}")
        else:
            print(f"  FALLA {modulo:13s} {MESES[mes-1]}{anio}")
            print(f"        esperaba {esperado}")
            print(f"        dio      {obtenido}")
            fallos.append(esperado)

    print("\nCierre que se lee de cada nombre de archivo")
    for nombre, esperado in CIERRES:
        obtenido = cierre_de(nombre)
        if obtenido == esperado:
            print(f"  ok    {nombre}")
        else:
            print(f"  FALLA {nombre} -> esperaba {esperado}, dio {obtenido}")
            fallos.append(nombre)

    print("\nUn nombre sin mes ni anio no se inventa un cierre")
    if cierre_de("cualquier-cosa.xlsx") is None:
        print("  ok    devuelve None")
    else:
        print("  FALLA se invento un cierre")
        fallos.append("sin periodo")

    print("\n" + "=" * 62)
    if fallos:
        print(f"{len(fallos)} prueba(s) no pasaron.\n")
        return 1
    print("Todo en orden.\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mes", help="cierre concreto, por ejemplo jun2026")
    ap.add_argument("--meses-atras", type=int, default=MESES_ATRAS,
                    help="cuantos meses retroceder buscando (por defecto 6)")
    ap.add_argument("--destino", default=str(DESTINO))
    ap.add_argument("--simular", action="store_true",
                    help="dice que haria, sin escribir nada")
    ap.add_argument("--probar", action="store_true",
                    help="comprueba la logica de nombres, sin tocar la red")
    args = ap.parse_args()

    if args.probar:
        return autoprueba()

    destino = Path(args.destino)
    destino.mkdir(parents=True, exist_ok=True)

    if args.mes:
        cierre = cierre_de(args.mes)
        if not cierre:
            print(f"[error] no entiendo el mes '{args.mes}'. "
                  f"Se escribe asi: jun2026")
            return 1
        ventana = 1
        hoy = cierre
    else:
        h = date.today()
        hoy = (h.year, h.month)
        ventana = args.meses_atras

    print(f"\nBuscando anexos GEIH en {BASE}")
    hallazgo = ultimo_publicado(hoy, ventana)
    if hallazgo is None:
        print("\n[nada] el DANE todavia no publica un mes completo.")
        print("       No se toca nada. Se reintenta en la proxima corrida.\n")
        return 2

    (anio, mes), urls = hallazgo
    etiqueta = f"{MESES[mes - 1]}{anio}"
    print(f"  ultimo cierre completo: {etiqueta}")

    # Que anexo de datos/ corresponde a cada modulo.
    #
    # El orden importa: 'anexgeih' es prefijo de los cuatro, asi que el
    # general solo puede reconocerse por descarte, cuando ya se descartaron
    # los que llevan sufijo de modulo (EISS, MLS, MLJ).
    actuales: dict[str, Path] = {}
    for archivo in sorted(destino.glob("*.xlsx")):
        n = norm(archivo.name)
        for modulo in ("informalidad", "sexo", "juventud", "general"):
            if modulo in actuales:
                continue
            if n.startswith(norm(MODULOS[modulo]["prefijo"])):
                actuales[modulo] = archivo
                break

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        nuevos: dict[str, Path] = {}
        for modulo, url in urls.items():
            nombre = url.rsplit("/", 1)[-1]
            print(f"  bajando {modulo:13s} {nombre}")
            datos = pedir(url)
            if datos is None:
                print(f"\n[nada] {url} se cayo a mitad de camino. "
                      f"No se toca nada.\n")
                return 2
            ruta = tmp / nombre
            ruta.write_bytes(datos)
            if not es_xlsx(ruta):
                print(f"\n[error] lo que llego en {nombre} no es un .xlsx.")
                print(f"        Suele pasar cuando el portal responde una "
                      f"pagina de error con codigo 200.")
                print(f"        No se toca datos/.\n")
                return 1
            nuevos[modulo] = ruta

        # Nada que hacer si los cuatro son byte a byte los que ya estan
        iguales = []
        for modulo, ruta in nuevos.items():
            viejo = actuales.get(modulo)
            iguales.append(bool(viejo and viejo.exists()
                                and sha256(viejo) == sha256(ruta)))
        if all(iguales):
            print(f"\n[nada] los cuatro anexos de {etiqueta} son identicos a "
                  f"los que ya estan.")
            print("       No se toca nada.\n")
            return 2

        if args.simular:
            print(f"\n[simulacro] entrarian {len(nuevos)} anexos de {etiqueta}.")
            for modulo, ruta in nuevos.items():
                marca = "igual" if iguales[list(nuevos).index(modulo)] else "NUEVO"
                print(f"            {marca:5s} {ruta.name}")
            print("            No se escribio nada.\n")
            return 0

        # Se instalan todos de una vez. Dejar mezclados anexos de dos meses
        # distintos es peor que no actualizar: localizar_anexos() se queda con
        # el mas reciente por fecha de archivo y podria emparejar mal.
        filas = []
        for modulo, ruta in nuevos.items():
            viejo = actuales.get(modulo)
            if viejo and viejo.exists() and viejo.name != ruta.name:
                viejo.unlink()
            final = destino / ruta.name
            shutil.copy2(ruta, final)
            filas.append((modulo, final.name, sha256(final), urls[modulo]))
            print(f"  [ok] {final.name}")

    # Rastro auditable: de que URL salio cada cifra y con que hash. Pesa un
    # renglon al mes y permite volver a bajar el archivo y comprobar que es
    # el mismo que produjo las cifras publicadas.
    historial = destino / HISTORIAL
    nuevo_historial = not historial.exists()
    with historial.open("a", encoding="utf-8") as f:
        if nuevo_historial:
            f.write("fecha;cierre;modulo;archivo;sha256;url\n")
        for modulo, nombre, h, url in sorted(filas):
            f.write(f"{date.today().isoformat()};{etiqueta};{modulo};"
                    f"{nombre};{h};{url}\n")

    print(f"\n[listo] {len(filas)} anexos de {etiqueta} en {destino}")
    print(f"        rastro en {historial}")
    print(f"        sigue: python etl.py && python verificar.py\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
