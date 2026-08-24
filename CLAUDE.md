# CLAUDE.md

Contexto del proyecto para cualquier sesión de trabajo en este repositorio.
Léelo completo antes de tocar nada. Buena parte de lo que sigue son decisiones
que ya se tomaron con criterio; cambiarlas sin entenderlas rompe las cifras.

---

## Qué es esto

Observatorio de mercado laboral de la **Cámara de Comercio de Cali**. Una
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
etl.py                       Lee los anexos del DANE -> docs/datos.json
verificar.py                 Pruebas de regresión sobre datos.json
construir_archivo_unico.py   Arma tablero-completo.html (versión portátil)
datos/                       Los cuatro anexos .xlsx del DANE
docs/                        Lo que se publica
  index.html                 El tablero entero: HTML + CSS + JS en un archivo
  datos.json                 Generado por etl.py. No se edita a mano.
  assets/
    LogoCCCPrincipal.jpg
    fonts/                   Ver LEEME.txt
tablero-completo.html        Versión de un solo archivo, abre con doble clic
.github/workflows/           Construye y publica en GitHub Pages
```

Ciclo mensual completo:

```bash
python etl.py                       # procesa los anexos nuevos
python verificar.py                 # confirma que nada se rompió
python construir_archivo_unico.py   # opcional: copia portátil
```

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

### 5. Detalles de las fuentes

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

Los arcos de las cabeceras y las tarjetas están generados por código en la
función `arcos()`, a partir de la descripción del manual: aros fragmentados en
seis partes, esquinas redondeadas, composiciones de uno a tres arcos con al
menos una esquina en contacto.

Son una interpretación. Si aparecen los archivos originales de la marca, hay
que reemplazarlos.

---

## Que esto se mantenga vivo

Este es el requisito central del proyecto, no un extra: el tablero tiene que
actualizarse **cada mes con las cifras nuevas, sin que nadie tenga que
acordarse de hacerlo**, y quedar publicado en el sitio de la CCC.

### Dónde está hoy

Semiautomático. El robot construye y publica solo, pero **una persona todavía
tiene que descargar los cuatro anexos del DANE y hacer commit**. Si esa persona
sale de vacaciones, el tablero se congela.

```
[persona] descarga 4 .xlsx  ->  commit  ->  [robot] ETL + verificar + publicar
   ^^^^^^^^ este eslabón es el que falta cerrar
```

### Cómo cerrarlo

Las URLs del DANE son predecibles. El anexo general vive en:

```
https://www.dane.gov.co/files/operaciones/GEIH/anex-GEIH-{mes}{anio}.xlsx
```

con `mes` en `ene feb mar abr may jun jul ago sep oct nov dic`. Por ejemplo
`anex-GEIH-jun2026.xlsx`. Ese patrón se mantiene estable desde abril de 2023.
Antes de esa fecha vivían en otra ruta y con otro nombre, lo cual es
exactamente la razón para no confiar ciegamente en el patrón.

Los otros tres anexos (EISS, MLS, MLJ) se publican en sus propias páginas
dentro del mismo portal y hay que verificar su patrón antes de automatizarlos.

**Diseño propuesto para `descargar.py`:**

1. Intenta la URL predecible del mes objetivo.
2. Si devuelve 404, busca el enlace en la página del DANE (es HTML plano, se
   puede leer con `urllib` + expresión regular sobre los `href` que terminen
   en `.xlsx`).
3. Si tampoco aparece, **no falla ruidosamente ni publica nada**: sale con un
   código que el workflow interpreta como "todavía no está disponible".
4. Compara el contenido descargado con el que ya está en `datos/`. Si es igual,
   termina sin hacer nada.
5. Solo si hay archivos nuevos, sigue el ETL.

**Cadencia:** el DANE publica el mercado laboral alrededor del día 30 del mes
siguiente, pero la fecha exacta se mueve. Un `cron` diario que casi siempre no
encuentra nada nuevo es más confiable que uno mensual que puede caer el día
equivocado. Algo como `0 14 * * *` (9 de la mañana en Colombia).

**La regla que no se negocia:** si `verificar.py` falla, el flujo **no
publica**. Es preferible que el sitio muestre las cifras del mes pasado a que
muestre cifras equivocadas con el logo de la Cámara encima. En ese caso el
workflow debe abrir un *issue* o mandar un correo, no seguir de largo.

**Qué hacer con los .xlsx descargados.** Dos opciones: comitearlos al repo
(deja rastro auditable de qué archivo produjo qué cifra, pero engorda el
historial ~14 MB al año) o procesarlos al vuelo sin guardarlos. Para una
entidad que cita cifras públicamente, la trazabilidad pesa más. Guardar solo
los del último mes y el hash de los anteriores es un punto medio razonable.

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

### Pendiente con insumos que ya deberían estar en el repo

1. **Extraer las morfologías y el logo en blanco de `CCC CLAUDE.pptx`.**
   El `.pptx` es un ZIP: las imágenes viven en `ppt/media/`. Buena parte del
   arte de plantilla viene en EMF o SVG. Reemplazar la función `arcos()` por
   los arcos reales y usar el logo blanco en el riel azul, en vez del
   contenedor blanco que hay hoy como solución de contraste.
   Slides: 1-2 logo, 3 morfologías para enmascarar, 4 morfologías para decorar,
   5-7 íconos, 8 íconos de redes.

2. **Sección de descargas con enlace a las fuentes.** Que cualquiera pueda
   bajar los anexos originales del DANE y el CSV procesado. Hoy el botón de
   descarga genera el CSV pero no hay enlace a los `.xlsx` de origen. Vale la
   pena que `etl.py` guarde también la URL de descarga del DANE en `meta`.

### Publicación y automatización

3. **Cerrar el ciclo con `descargar.py`**, según el diseño de la sección
   anterior. Es lo que convierte el tablero en algo vivo. Empezar por el anexo
   general, que tiene el patrón confirmado, y después verificar los otros tres.

4. **Dejar andando GitHub Pages** con el workflow que ya está en
   `.github/workflows/publicar.yml`. Agregarle el `cron` diario y el paso de
   descarga, y hacer que abra un *issue* cuando algo falle.

5. **Ayudar a incrustarlo en WordPress.** El `iframe` de altura fija es
   incómodo. Vale la pena un pequeño script `postMessage` que le informe al
   contenedor la altura real, con instrucciones para el equipo de web. En
   celular conviene ofrecer el enlace directo en vez del `iframe`.

6. **Enlaces compartibles.** Que la sección, el modo temporal, el período y
   las ciudades comparadas queden en el hash de la URL. Es lo que permite
   mandar por correo "mira la informalidad de Cali en 2024" y que abra ahí.
   Importante para una entidad que cita cifras.

### Calidad

7. **Accesibilidad.** Las gráficas SVG necesitan `<title>` y `aria-label`
   descriptivos, y una alternativa en tabla para lectores de pantalla. Revisar
   contraste de los textos secundarios sobre blanco maceta.

8. **Metadatos.** `og:image`, `og:description`, favicon con el isotipo. Cuando
   alguien comparta el enlace en LinkedIn o WhatsApp, tiene que verse la marca.

9. **Peso.** `datos.json` pesa 1,75 MB (unos 400 KB comprimido). Se puede
   bajar bastante separando el archivo por módulo y cargando bajo demanda, o
   recortando la precisión de los niveles. No es urgente, pero en conexiones
   lentas se nota.

### Referencia de diseño

10. **Revisar el monitor de la Secretaría de Desarrollo Económico de Bogotá**
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
