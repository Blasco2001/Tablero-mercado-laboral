# CLAUDE.md

Contexto del proyecto para cualquier sesión de trabajo en este repositorio.
Léelo completo antes de tocar nada. Buena parte de lo que sigue son decisiones
que ya se tomaron con criterio; cambiarlas sin entenderlas rompe las cifras.

---

## Qué es esto

**Visor de seguimiento al mercado laboral** de la **Cámara de Comercio de Cali**. Una
aplicación web estática que publica los indicadores de mercado laboral de
**Cali A.M.**, con fuente en la Gran Encuesta Integrada de Hogares (GEIH) del
DANE, y permite compararlos contra las otras 22 ciudades y áreas
metropolitanas.

Se va a publicar en el sitio institucional de la CCC (WordPress). El modelo de
publicación es el mismo que se usaba con Power BI: el tablero vive en su propia
URL y desde la página se enlaza o se incrusta.

**El foco es Cali A.M.** Las demás ciudades existen para comparar, no para
competir por el protagonismo. Cualquier vista nueva debe responder primero
"¿cómo está Cali?" y solo después "¿frente a quién?".

---

## Cómo está armado

```
descargar.py                 Trae los anexos del DANE -> datos/
etl.py                       Lee los anexos del DANE -> docs/datos.json
verificar.py                 Pruebas de regresión sobre datos.json
construir_archivo_unico.py   Arma tablero-completo.html (versión portátil)
datos/                       Los cuatro anexos .xlsx del DANE
  historial.csv              Rastro auditable: sha256 y URL de cada descarga
docs/                        Lo que se publica
  index.html                 El tablero entero: HTML + CSS + JS en un archivo
  datos.json                 Generado por etl.py. No se edita a mano.
  assets/
    logo-ccc-blanco.svg      Logo en blanco, para el riel azul
    LogoCCCPrincipal.jpg     Logo a color, sin usar hoy (sirve para og:image)
    fonts/                   Ver LEEME.txt
tablero-completo.html        Versión de un solo archivo, abre con doble clic
.github/workflows/           Construye y publica en GitHub Pages
```

Ciclo mensual completo. **Normalmente no hay que correrlo**: el workflow lo
hace solo todos los días. Esto es para trabajar en local o para reconstruir a
mano si algo falló:

```bash
python descargar.py                 # busca anexos nuevos en el DANE
python etl.py                       # los procesa
python verificar.py                 # confirma que nada se rompió
python construir_archivo_unico.py   # opcional: copia portátil
```

`descargar.py` sale con código 2 cuando no hay nada nuevo, que es lo normal
casi todos los días.

### Sin dependencias

Las gráficas son **SVG generado a mano** en `index.html`: líneas, barras
horizontales, barras apiladas, anillo y cascada de población. No hay Chart.js,
ni D3, ni bundler, ni paso de compilación. Fue una decisión deliberada: el
tablero tiene que sobrevivir años en un servidor institucional sin que nadie le
haga mantenimiento, y cada CDN es una dependencia que algún día se cae.

**No metas librerías de gráficas.** Si necesitas un tipo de gráfica nueva,
escríbela en el mismo estilo que las que ya están.

### Dos formas de servir los mismos datos

`index.html` mira si existe un `<script id="datos-embebidos">` en el documento.
Si está, lo usa; si no, pide `datos.json` con `fetch`. Es un solo código base.

Consecuencia práctica: **`docs/index.html` no funciona con doble clic**. El
navegador bloquea `fetch` bajo `file://`. Para probarlo en local:

```bash
cd docs && python -m http.server 8000
```

`tablero-completo.html` sí abre con doble clic porque lleva los datos y el logo
incrustados. No borres esa ruta doble.

---

## Reglas de datos que no se pueden romper

Cada una está protegida por una prueba en `verificar.py`. Si una falla, no
ajustes la prueba: entiende qué pasó.

### 1. Un cero exacto del DANE no es un dato

Los anexos rellenan con `0` los períodos que no se midieron. El caso claro es
la subocupación entre Ene-Mar y Jul-Sep de 2020, cuando la pandemia interrumpió
la recolección. Dibujar eso como cero produce un desplome que nunca ocurrió.

`num()` en `etl.py` devuelve `None` ante un cero exacto. En un área
metropolitana de millones de habitantes ninguna población ni tasa de este
tablero puede valer exactamente cero.

Las gráficas de línea dibujan el hueco: `lineas()` parte el trazo en tramos y
no une los extremos. Unirlos inventaría una trayectoria que nadie midió.

### 2. El promedio del año son cuatro trimestres que no se traslapan

Ene-Mar, Abr-Jun, Jul-Sep y Oct-Dic. Cada mes del año entra exactamente una
vez. Esta definición la fijó la CCC y reproduce la cifra oficial del DANE:
Cali A.M. en 2025 da 8,75% de desempleo y 1.115.000 ocupados, contra 8,746% y
1.115.100 publicados.

**Los niveles se promedian. Las tasas se recalculan a partir de esos niveles.**
Promediar tasas directamente sesga el resultado hacia los trimestres con menos
población. Esto vale en el ETL y en cualquier cálculo nuevo del front.

Si a un año completo le falta algún trimestre, el promedio queda vacío. Un
promedio con huecos no es el del año: es el de los meses que sobrevivieron.

Se descartó el **año móvil**: no lo necesita el proyecto. Solo existen dos
modos temporales, trimestre móvil y promedio anual.

### 3. Un año a medias no se compara contra uno entero

2026 llega hasta junio. Compararlo contra 2025 completo da +0,3 pp; contra
Ene-Jun de 2025 da −0,7 pp. La segunda es la cifra correcta.

`referencia_anual` en `datos.json` guarda, para cada año, el valor del año
anterior medido con el mismo número de trimestres. Las tarjetas KPI lo usan y
la etiqueta lo dice en voz alta: "vs. 2025 (Ene-Jun)".

### 4. El ETL busca por etiqueta, nunca por número de fila

Los anexos del DANE cambian de nombre cada mes y crecen en columnas.

- **Archivos**: por patrón de nombre. `EISS` → informalidad, `MLJ` → juventud,
  `MLS` → sexo, el resto `anexGEIH*` → general.
- **Bloques de ciudad**: por el nombre en la columna A, normalizado sin tildes
  ni mayúsculas.
- **Indicadores**: por el comienzo de su etiqueta.
- **Períodos**: anclados. La primera columna de trimestre móvil termina en
  marzo de 2007; la columna *i* termina *i* meses después. Informalidad se
  ancla en marzo de 2021.

**No introduzcas índices fijos de fila o columna.** Es lo que hace que el
proceso sobreviva a las actualizaciones del DANE.

### 5. El enlace guarda el período por código, no por posición

El estado de la vista vive en el hash de la URL:

```
#seccion=informal&modo=an&periodo=2024&desde=2021&ciudades=Bogota%20D.C.
```

El período va como **código** (`2024`, `2026-06`), nunca como índice. La grilla
de trimestres crece uno cada mes: un enlace que dijera "posición 231"
apuntaría a junio hoy y a julio el mes entrante, y quien lo abriera vería una
cifra distinta de la que le mandaron sin enterarse de nada. Para una entidad
que cita cifras, eso es peor que un enlace roto.

Cada campo se valida contra los datos que existan al abrirlo. Un enlace de hace
un año puede nombrar un período o una ciudad que ya no están; en ese caso se
ignora ese campo y se abre en lo que sí exista. Un enlace viejo se degrada, no
se rompe.

`escribirHash()` se llama desde `render()` y de ningún otro lado: es el único
punto por el que pasan todos los cambios de estado, así que el enlace no puede
quedar desfasado. Va con `replaceState` para no llenar el historial con una
entrada por clic — dentro de un `try`, porque en `tablero-completo.html` el
origen es `null` y `replaceState` lanza `SecurityError`. Sin ese `try` la
versión de doble clic se caería en cada render.

### 6. Detalles de las fuentes

- Las poblaciones vienen en miles; el front las convierte a personas al mostrar.
- La informalidad solo existe desde el primer trimestre de 2021, por el cambio
  metodológico de la GEIH. Las gráficas recortan solas el tramo vacío inicial.
- Los NINI quedaron fuera a propósito: el DANE solo los publica a nivel
  nacional y el foco es Cali.
- Cali A.M. incluye a Cali y Yumbo.

---

## Identidad visual

Sale del **Nexus Design System**, el manual de identidad de la CCC (versión 6.2,
mayo de 2026). Todos los colores están declarados con su nombre de marca en el
bloque `:root` al comienzo de `index.html`.

**Paleta principal:** azul sereno `#12176B`, azul pacífico `#253D90`, azul
farallones `#6FBCFF`, blanco maceta `#FAFAFA`.

**Paleta secundaria:** violeta guayacán `#5F27B5`, verde feijó `#65D7B7`,
chontaduro `#F2661F`, verde viche `#99DD3A`, magenta arrebol `#EF0074`.

Cada sección tiene su momento cromático en la constante `TEMAS`.

### Reglas del manual, ya aplicadas

- **Proporción 95 / 5.** La paleta principal domina la composición; el color
  temático es acento, no relleno. Por eso las barras de ranking son azules
  aunque la sección sea violeta o naranja.
- **Gradaciones solo verticales (90°), con el tono oscuro en la base.**
- **Extremos redondeados** en barras y líneas.
- **Datos ordenados por tamaño**, de mayor a menor.
- **Titulares sin mayúsculas sostenidas y sin itálicas.** El manual es
  explícito: las mayúsculas se leen como un grito y chocan con la cercanía que
  busca la marca. Las itálicas están prohibidas en la tipografía principal.
- **Números tabulares** en tablas y gráficas.

### Tipografía

Savior Sans Expanded (Sudtipos) para títulos, Libertad (TipoType) para texto.
Ambas comerciales. Los `@font-face` ya están declarados apuntando a
`docs/assets/fonts/`; apenas aparezcan los `.woff2` entran solas.

Mientras tanto: **Encode Sans Expanded** sustituye a Savior Sans Expanded y
**Source Sans 3** a Libertad, desde Google Fonts.

Advertencia para la CCC: la licencia de escritorio de esas fuentes no cubre
publicarlas en un sitio web. Se necesita licencia *webfont*.

### Morfologías

Los trazos son **el arte original de la marca**, extraído de
`marca/CCC_PlantillaPPTX.pptx` (slide 4) y guardado en la constante
`MORFOLOGIAS` de `index.html`. Ya no son una interpretación.

Las reglas, verificadas contra el brandbook (págs. 79-86):

- Los aros nacen del concepto **Nexo Vital**: tres aros por los tres motores de
  la CCC — capital social, empresas esenciales, conexión global.
- Se **fragmentan en seis partes iguales**. De ahí sale el arco, que es la
  unidad mínima y existe en **tres tamaños**, uno por aro.
- **Un arco solo lleva todas sus esquinas redondeadas.**
- **En composición, las esquinas que se tocan o se alinean van RECTAS**; las
  que quedan libres conservan el redondeo. Esto es más preciso de lo que decía
  antes esta nota ("al menos una esquina en contacto"): lo que manda no es que
  se toquen, sino cómo se resuelve la esquina cuando se tocan.
- Las composiciones van **de uno a tres arcos**, y pueden mezclar arcos de
  distintos tamaños.

**Los colores no se copian del arte.** El original viene siempre en azules;
cada trazo guarda su nivel de tono (0 el más oscuro, 2 el más claro) y quien
llama a `arcos()` decide qué color va en cada nivel. Así cada sección conserva
su momento cromático. Por eso `TEMAS` tiene un tercer tono, `claro`, tomado de
las escalas UI del Nexus que ya estaban en `:root`.

En el riel azul la jerarquía **se invierte**: el trazo que en el arte es el más
oscuro se dibuja con el tono más claro del tema, o desaparece contra el fondo.

El azul sereno del arte venía como `#12186B`, un dígito por debajo del
`#12176B` que fija el brandbook. Se normalizó. Es una inconsistencia del PPTX,
no un cambio de marca: sus propios íconos de redes traen el valor bueno. Lo
mismo con el violeta de los íconos, `#5E26B5` contra `#5F27B5`.

---

## Que esto se mantenga vivo

Este es el requisito central del proyecto, no un extra: el tablero tiene que
actualizarse **cada mes con las cifras nuevas, sin que nadie tenga que
acordarse de hacerlo**, y quedar publicado en el sitio de la CCC.

### Dónde está hoy

Cerrado. `descargar.py` trae los cuatro anexos del DANE y el workflow corre
solo todos los días a las 9 de la mañana. Nadie tiene que acordarse de nada.

```
[cron diario] -> descargar.py -> etl.py -> verificar.py -> GitHub Pages
                      |              |          |
                   nada nuevo?    falla?     falla?
                    termina       issue      issue, NO publica
```

### Las URLs del DANE

Los cuatro patrones están **comprobados contra el portal**, no supuestos:

```
general        anex-GEIH-{mes}{anio}.xlsx              anex-GEIH-jun2026.xlsx
informalidad   anex-GEIHEISS-{trimestre}.xlsx          anex-GEIHEISS-abr-jun2026.xlsx
sexo           anex-GEIHMLS-{trimestre}.xlsx           anex-GEIHMLS-abr-jun2026.xlsx
juventud       anex-GEIHMLJ-{trimestre}.xlsx           anex-GEIHMLJ-abr-jun2026.xlsx
```

Todos cuelgan de `https://www.dane.gov.co/files/operaciones/GEIH/`. Ojo con
tres cosas que no se adivinan:

1. **No hay guion entre `GEIH` y el módulo.** Es `anex-GEIHEISS-`, no
   `anex-GEIH-EISS-`. Esa segunda forma da 404.

2. **El general se nombra por el mes de cierre; los otros tres, por el
   trimestre completo.** El mismo período es `jun2026` para uno y
   `abr-jun2026` para los otros.

3. **Cuando el trimestre cruza el fin de año, cada extremo carga el suyo.**

   ```
   abr-jun2026        mismo año
   dic2025-feb2026    a caballo entre dos años
   dic-feb2026        ← 404. Es la forma que uno escribiría por analogía.
   ```

   Esto muerde tres meses al año: los trimestres que cierran en enero, febrero
   y marzo. `nombre_esperado()` en `descargar.py` lo maneja, y hay una prueba
   que lo cubre.

El patrón se mantiene estable desde abril de 2023; antes vivían en otra ruta y
con otro nombre. Por eso `descargar.py` no confía solo en el patrón: si la URL
directa da 404, lee la página del módulo y saca el enlace de ahí. Cuidado al
tocar ese respaldo, porque en las mismas páginas cuelgan el anexo
desestacionalizado, los de RELAB y el de economía creativa, que este tablero no
usa; el filtro por prefijo exacto es lo que los deja fuera.

### Por qué espera a que estén los cuatro

`descargar.py` no actualiza nada hasta que los cuatro módulos existen **para el
mismo mes de cierre**. No es prudencia de más:

El módulo general fija la grilla de períodos del ETL (`cod_tm`). Informalidad
se realinea con `alinear()`, pero **sexo y juventud se leen sin realinear**. Si
uno llega un mes tarde, sus series quedan más cortas que la grilla y
`verificar.py` lo tumba con "todas las series miden lo mismo que la grilla".

Es decir: la red de seguridad funciona, pero saltaría en falso cada mes que el
DANE se desacompase. Antes que enseñar a ignorar una alarma roja, se espera.

### Los códigos de salida son la interfaz

`descargar.py` le habla al workflow por el código de salida. No son adorno:

| código | significa | qué hace el workflow |
|--------|-----------|----------------------|
| `0` | hay anexos nuevos | ETL, verificar, comitear, publicar |
| `2` | nada que hacer: el DANE no ha publicado, o ya estamos al día | termina en silencio |
| `1` | error de verdad | abre un *issue*, no publica |

Un corte de red devuelve `2`, no `1`. Un cron diario contra un portal público
se va a topar con caídas, y una caída no es motivo para despertar a nadie:
mañana lo vuelve a intentar. Lo que sí devuelve `1` es un archivo corrupto —
cuando el portal está en mantenimiento contesta una página de error con código
200 y extensión `.xlsx`, y esa página **no** puede entrar a `datos/`. Por eso
se comprueba que cada descarga sea un ZIP con un `xl/` adentro.

**La regla que no se negocia:** si `verificar.py` falla, el flujo **no
publica**. Es preferible que el sitio muestre las cifras del mes pasado a que
muestre cifras equivocadas con el logo de la Cámara encima. El workflow abre un
*issue* (y comenta en el que ya esté abierto, en vez de abrir uno nuevo cada
día).

### Qué queda de los .xlsx descargados

Se comitean. Para una entidad que cita cifras públicamente la trazabilidad pesa
más que los ~14 MB al año de historial.

Además `datos/historial.csv` guarda un renglón por descarga con fecha, cierre,
módulo, nombre, **sha256 y URL de origen**. Con eso se puede volver a bajar el
archivo meses después y comprobar que es exactamente el que produjo las cifras
publicadas.

Si algún día el historial pesa demasiado, el `historial.csv` es lo que permite
dejar de comitear los `.xlsx` sin perder la auditoría.

### Certificados

`descargar.py` usa `certifi` **solo si el Python que lo corre no trae almacén
de certificados** (`ssl.get_default_verify_paths().cafile` es `None`, que pasa
en algunos Python de macOS). En Linux, que es donde corre el workflow, no hace
falta y no se usa. Nunca se apaga la verificación: da lo mismo que sean cifras
públicas, bajarlas sin verificar el certificado sería confiar en cualquiera que
se meta en medio.

Si en tu máquina toda descarga falla con `self-signed certificate in
certificate chain`, no es el DANE: es tu Python. Se arregla con
`pip install certifi`.

### Nombres de archivo

`localizar_anexos()` normaliza el nombre quitando guiones, espacios y
paréntesis antes de clasificar. Eso hace que `anex-GEIH-jun2026.xlsx` (como lo
sirve el DANE) y `anexGEIHjun2026 (2).xlsx` (como lo guarda el navegador)
lleguen al mismo lugar. También ignora explícitamente los anexos vecinos que
el tablero no usa: desestacionalizado, RELAB y economía creativa.

Si aparece un módulo nuevo, va en esa misma función.

---

## Qué falta

Ordenado por lo que más aporta primero.

### Insumos de marca

Los originales están en `marca/`: `CCC_PlantillaPPTX.pptx` (53 MB),
`CCC_Brandbook_2026.pdf` (24 MB) y `fuentes/`. El `.pptx` es un ZIP y sus
imágenes viven en `ppt/media/`: **255 SVG y 258 PNG, ningún EMF**, así que no
hay que convertir nada.

Qué hay en cada slide: 1-2 logo (azul y blanco, cuatro proporciones cada uno),
3 morfologías para enmascarar, 4 morfologías para decorar, 5-7 íconos, 8 íconos
de redes.

Ya integrados: las morfologías del slide 4 y el logo blanco del slide 2.

1. **Queda pendiente, si algún día hace falta:**
   - Las **224 iconos** de los slides 5 a 8 (mediana ~1,2 KB). No se
     extrajeron porque hoy el tablero no tiene dónde ponerlos: la navegación
     usa las morfologías. Los 7 del slide 8 son de redes sociales y ya vienen
     en el azul sereno correcto.
   - Las **morfologías para enmascarar del slide 3**, que no son imágenes sino
     cuatro formas nativas de PowerPoint (`custGeom`). Convertirlas exige
     interpretar geometría DrawingML. Sirven para recortar fotografías, algo
     que este tablero no hace.

**`marca/fuentes/` está en `.gitignore`**, a propósito. Solo trae `.otf` y
`.ttf` — formato de escritorio —, no hay ningún archivo de licencia en la
carpeta, y las fuentes no declaran términos: el metadato de licencia viene
vacío y el copyright dice "All rights reserved". Comitearlas en un repo que se
hace público para GitHub Pages sería redistribuirlas.

### Publicación

**No hay trabajo de incrustación.** Se verificó la página del Visor de Datos de
la CCC (`ccc.org.co/informacion-y-estudios-economicos/visor-de-datos/`) y **no
incrusta tableros**: es una lista de botones que abren enlaces externos. Los
visores actuales viven en `app.powerbi.com` y `public.tableau.com`, y el único
`iframe` de la página es un video de YouTube.

Eso simplifica todo. El tablero vive en su propia URL y desde la página de la
CCC se enlaza, igual que los demás visores. No hace falta el script de
`postMessage` para la altura del `iframe` que se había previsto.

2. **Dejar andando GitHub Pages.** El workflow ya está completo (cron diario,
   descarga, ETL, verificación, *issue* al fallar), pero falta el paso manual
   que nadie puede automatizar: entrar a Settings -> Pages del repositorio y
   elegir **GitHub Actions** como origen. Hasta que alguien haga eso, el
   workflow corre y falla en el último paso.

   Publica en `https://blasco2001.github.io/Tablero-mercado-laboral/`.

3. **Activar el subdominio propio**, `observatoriolaboral.ccc.org.co`.

   **El orden importa y hacerlo al revés tumba el sitio.** Con un archivo
   `CNAME` presente, GitHub Pages redirige `blasco2001.github.io` al dominio
   propio; si el DNS todavía no resuelve, el tablero queda inalcanzable por
   las dos rutas. Por eso el archivo está preparado como
   `docs/CNAME.pendiente` y **no** como `docs/CNAME`.

   La secuencia:

   1. Dejar andando Pages (punto 2) y comprobar que el tablero abre en la URL
      de `github.io`.
   2. Pedirle a TI de la CCC este registro DNS:

      ```
      Tipo    CNAME
      Nombre  observatoriolaboral
      Valor   blasco2001.github.io
      TTL     3600
      ```

   3. Cuando `dig observatoriolaboral.ccc.org.co` responda, y solo entonces:

      ```bash
      git mv docs/CNAME.pendiente docs/CNAME
      git commit -m "Activar el subdominio observatoriolaboral.ccc.org.co"
      git push
      ```

   4. En Settings -> Pages, marcar **Enforce HTTPS** cuando GitHub termine de
      emitir el certificado (tarda unos minutos).

4. **Pasarle al equipo de web el texto del botón.** Redactado y listo en
   `BOTON-VISOR.md`, siguiendo el estilo de los que ya están en esa
   página. Falta mandárselo cuando la URL definitiva esté en pie.

### Calidad

5. **Accesibilidad.** Las gráficas SVG necesitan `<title>` y `aria-label`
   descriptivos, y una alternativa en tabla para lectores de pantalla. Revisar
   contraste de los textos secundarios sobre blanco maceta.

6. **Metadatos.** `og:image`, `og:description`, favicon con el isotipo. Cuando
   alguien comparta el enlace en LinkedIn o WhatsApp, tiene que verse la marca.

7. **Peso.** `datos.json` pesa 1,75 MB (unos 400 KB comprimido). Se puede
   bajar bastante separando el archivo por módulo y cargando bajo demanda, o
   recortando la precisión de los niveles. No es urgente, pero en conexiones
   lentas se nota.

### Referencia de diseño

8. **Revisar el monitor de la Secretaría de Desarrollo Económico de Bogotá**
   (`https://observatorio.desarrolloeconomico.gov.co/monitor-mercado-laboral-en-cifras/`),
   que es la referencia que pidió el cliente. Extraer ideas de estructura y
   navegación, no de estética: la identidad visual acá es la de la CCC.

---

## Cómo verificar antes de dar algo por hecho

```bash
python etl.py && python verificar.py
```

Y abrir el tablero de verdad en un navegador. Los errores que importan —
etiquetas encimadas, series que no pintan, paneles vacíos — no salen en la
consola. Recorrer las siete secciones en los dos modos temporales, cambiar
período, agregar y quitar ciudades, y mirarlo en ancho de celular.

---

## Cómo trabajar aquí

- **El español es el idioma del proyecto.** Interfaz, comentarios, nombres de
  variables, mensajes de commit. Ya está así; mantenerlo.
- **Los comentarios explican por qué, no qué.** Los que hay marcan las
  decisiones difíciles: por qué un cero no es un dato, por qué no se promedian
  tasas, por qué el SVG mide el ancho real del panel. Ese es el estándar.
- **Ante una cifra rara, sospecha primero de la fuente.** Los anexos del DANE
  tienen rellenos, cambios de metodología y convenciones inconsistentes de un
  año a otro. Ya aparecieron tres.
- **Nada de datos inventados ni de ejemplo.** Si algo no se puede calcular,
  queda vacío y se dice por qué.
