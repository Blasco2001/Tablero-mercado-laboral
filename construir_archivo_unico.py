#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Construye una version del tablero en UN SOLO ARCHIVO.
=====================================================

El tablero publicado pide los datos con fetch(), y los navegadores bloquean
fetch() cuando la pagina se abre con doble clic (protocolo file://). Por eso
existe esta version: mete los datos y el logo dentro del propio HTML, asi que
funciona en cualquier parte -- doble clic, memoria USB, adjunto de correo o
un servidor web.

Uso:
    python construir_archivo_unico.py

Produce:
    tablero-completo.html

Pesa mas que la version publicada (los datos van adentro), pero no depende
de nada externo salvo las fuentes de Google, que solo cambian el aspecto.
"""

import base64
import json
import mimetypes
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
HTML = RAIZ / "docs" / "index.html"
DATOS = RAIZ / "docs" / "datos.json"
ASSETS = RAIZ / "docs" / "assets"
SALIDA = RAIZ / "tablero-completo.html"


def a_data_uri(ruta: Path) -> str:
    tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
    return f"data:{tipo};base64," + base64.b64encode(ruta.read_bytes()).decode("ascii")


def main():
    for f in (HTML, DATOS):
        if not f.exists():
            sys.exit(f"[ERROR] Falta {f}. Ejecuta primero: python etl.py")

    html = HTML.read_text(encoding="utf-8")
    datos = json.loads(DATOS.read_text(encoding="utf-8"))

    # 1. Las imagenes se vuelven data URI para que no haya rutas que se rompan
    n_img = 0
    for tag in set(re.findall(r'src="(assets/[^"]+)"', html)):
        archivo = RAIZ / "docs" / tag
        if archivo.exists():
            html = html.replace(f'src="{tag}"', f'src="{a_data_uri(archivo)}"')
            n_img += 1

    # 2. Los datos entran como bloque JSON. Se escapa "<" para que ningun
    #    contenido pueda cerrar el <script> antes de tiempo.
    crudo = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    bloque = f'<script id="datos-embebidos" type="application/json">{crudo}</script>\n<script>\n'
    if '<script id="datos-embebidos"' in html:
        html = re.sub(r'<script id="datos-embebidos".*?</script>\n', "", html, flags=re.S)
    html = html.replace('<script>\n"use strict";', bloque + '"use strict";', 1)

    # 3. Si las fuentes de marca aun no estan, se quitan sus @font-face:
    #    de lo contrario el navegador intenta cargarlas y llena la consola
    #    de errores que no significan nada.
    faltan = [n for n in re.findall(r"url\('(assets/fonts/[^']+)'\)", html)
              if not (RAIZ / "docs" / n).exists()]
    if faltan:
        html = re.sub(r"@font-face\{[^}]*assets/fonts/[^}]*\}\n?", "", html)
        print(f"        {len(faltan)} fuente(s) de marca no están todavía: se usan las sustitutas")

    # 4. Aviso al pie para que nadie confunda esta copia con la publicada
    html = html.replace(
        "<span id=\"pie-act\"></span>",
        "<span id=\"pie-act\"></span><br><span style=\"opacity:.75\">"
        "Copia de archivo único.</span>")

    SALIDA.write_text(html, encoding="utf-8")
    mb = SALIDA.stat().st_size / 1e6
    print(f"\n[listo] {SALIDA.name}  ({mb:.1f} MB)")
    print(f"        {n_img} imagen(es) incrustada(s)")
    print(f"        último trimestre móvil: {datos['meta']['ultimo_tm']}")
    print("        Se abre con doble clic. No necesita servidor.\n")


if __name__ == "__main__":
    main()
