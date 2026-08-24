# Observatorio de mercado laboral · Cámara de Comercio de Cali

Tablero interactivo con las cifras de mercado laboral de **Cali A.M.**, con
fuente en la Gran Encuesta Integrada de Hogares del DANE.

---

## Ver el tablero

Hay dos versiones del mismo tablero. Elige según lo que necesites.

### Para mirarlo ahora mismo · `tablero-completo.html`

Doble clic y listo. Los datos y el logo van dentro del archivo, así que no
necesita nada más: funciona desde el escritorio, una memoria USB o un adjunto
de correo. Pesa 1,9 MB.

Se regenera con:

```bash
python construir_archivo_unico.py
```

Sirve para revisar, para mostrarlo en una reunión y para mandarlo por correo.
No sirve para publicar en el sitio web.

### Para publicar · la carpeta `docs/`

Esta es la versión que va al servidor. Es más liviana y separa el tablero de
los datos, así que actualizar el mes siguiente solo cambia el `datos.json`.

**Ojo con esto:** `docs/index.html` pide los datos con `fetch`, y los
navegadores bloquean `fetch` cuando la página se abre con doble clic
(protocolo `file://`). Si lo abres así verás la pantalla de carga y nada más.
No está dañado: necesita servirse por HTTP.

Para verla en tu computador antes de publicar:

```bash
cd docs
python -m http.server 8000
```

y abres `http://localhost:8000`.

---

```
observatorio-mercado-laboral/
├── datos/                  ← aquí van los cuatro anexos del DANE
│   ├── anexGEIHjun2026_2.xlsx           (general)
│   ├── anexGEIHMLSabrjun2026.xlsx       (sexo)
│   ├── anexGEIHEISSabrjun2026.xlsx      (informalidad)
│   └── anexGEIHMLJabrjun2026_1.xlsx     (juventud)
├── CLAUDE.md               ← contexto y reglas del proyecto
├── etl.py                  ← convierte los anexos en datos.json
├── verificar.py            ← pruebas de regresión sobre los datos
├── construir_archivo_unico.py  ← arma tablero-completo.html
├── tablero-completo.html   ← versión de un solo archivo, abre con doble clic
├── docs/                   ← esto es lo que se publica
│   ├── index.html          ← el tablero completo
│   ├── datos.json          ← generado por etl.py, no se edita a mano
│   └── assets/
│       ├── LogoCCCPrincipal.jpg
│       └── fonts/          ← ver LEEME.txt
└── .github/workflows/publicar.yml
```

---

## Actualizar cada mes

Cuatro pasos, unos dos minutos.

1. Descarga los cuatro anexos nuevos del DANE.
2. Ponlos en `datos/` y borra los del mes anterior.
3. Ejecuta:

   ```bash
   python etl.py
   python verificar.py
   ```

   `verificar.py` comprueba que las cifras siguen cuadrando con lo que publica
   el DANE y que las decisiones metodológicas siguen en pie. Si algo falla,
   dice qué y no deberías publicar hasta resolverlo.

4. Publica el contenido de `docs/`.

Si además quieres la copia de un solo archivo para circular por correo,
agrega `python construir_archivo_unico.py` después del paso 3.

Eso es todo. No hay que abrir `index.html` ni tocar nada más.

### Por qué no se rompe

`etl.py` no depende de números de fila ni de columna. Busca las cosas por su
etiqueta de texto:

- **Los archivos**, por patrón de nombre (`EISS` → informalidad, `MLJ` →
  juventud, `MLS` → sexo, el resto → general). Da igual que cambie el sufijo
  del mes.
- **Los bloques de ciudad**, por el nombre de la ciudad en la columna A,
  ignorando tildes y mayúsculas.
- **Los indicadores**, por el comienzo de su etiqueta (`Tasa de desocupación…`).
- **Los períodos**, anclados en que la primera columna de datos es el trimestre
  que termina en marzo de 2007. La columna *i* termina *i* meses después.

Si el DANE agrega períodos, mueve un bloque o renombra un archivo, sigue
funcionando. Si cambia el nombre de una hoja o de un indicador, el proceso
avisa en pantalla en vez de producir datos silenciosamente equivocados.

### Comprobación rápida después de actualizar

El script imprime cuántas ciudades y períodos leyó de cada módulo, y cuál es
el último trimestre. Si el último trimestre no es el que esperabas, algo pasó
con los archivos de entrada.

---

## Publicar

### Opción A · GitHub Pages (recomendada, gratis, automática)

Con el repositorio en GitHub y Pages activado apuntando a GitHub Actions, el
flujo del mes se reduce a: reemplazar los `.xlsx` en `datos/`, hacer commit y
push. El workflow ejecuta el ETL, revisa que el JSON quedó bien y publica.

La URL queda del tipo `https://<organizacion>.github.io/<repositorio>/`.

### Opción B · Servidor propio

`docs/` es un sitio estático: HTML, un JSON y una imagen. No necesita PHP,
base de datos ni Node. Súbelo por FTP a cualquier carpeta pública.

**Importante:** el tablero carga `datos.json` con `fetch`, así que tiene que
servirse por HTTP. Abrir `index.html` con doble clic no funciona. Para probarlo
en local:

```bash
cd docs && python -m http.server 8000
# luego abrir http://localhost:8000
```

### Ponerlo en la página de la CCC

Igual que hacían con Power BI: publicas el tablero en su propia URL y esa URL
se enlaza o se incrusta. Para incrustarlo dentro de una página de WordPress,
en un bloque **HTML personalizado**:

```html
<iframe src="https://TU-URL-DEL-TABLERO/"
        style="width:100%;height:1400px;border:0"
        title="Observatorio de mercado laboral · Cámara de Comercio de Cali"
        loading="lazy"></iframe>
```

Un enlace directo funciona mejor en celular, donde el `iframe` queda apretado.
Vale la pena ofrecer las dos cosas.

---

## Qué contiene el tablero

| Sección | Qué muestra | Desde |
|---|---|---|
| Resumen | Indicadores principales de Cali A.M. y ranking de ciudades | 2007 |
| Panorama general | Desempleo, ocupación, participación, subocupación y niveles | 2007 |
| Brechas de género | Los mismos indicadores separados por sexo, más las brechas | 2007 |
| Informalidad | Proporción y composición formal/informal | 2021 |
| Juventud | Mercado laboral de 15 a 28 años | 2007 |
| Comparativo ciudades | Ranking, puesto de Cali en el tiempo y tabla completa | 2007 |
| Datos y método | Fuentes, metodología y advertencias de lectura | — |

**Controles:** agregación temporal (trimestre móvil o promedio anual), período,
año de inicio de la serie, y hasta siete ciudades de comparación. Además,
descarga de los datos en CSV y exportación a PDF.

### El promedio anual

Se calcula con los cuatro trimestres móviles que **no se traslapan**:
Ene-Mar, Abr-Jun, Jul-Sep y Oct-Dic. Cada mes del año entra exactamente una vez.

Los niveles de población se promedian; las tasas se **recalculan** a partir de
esos niveles. Promediar tasas directamente sesgaría el resultado hacia los
trimestres con menos población.

*Comprobación:* para Cali A.M. en 2025 este método da 8,75% de desempleo y
1.115.000 ocupados. El DANE publica 8,746% y 1.115.100 para el año completo.

**Año en curso:** cuando un año todavía no tiene los cuatro trimestres, se
promedia con los que haya y aparece marcado — *2026 (Ene-Jun)*. La comparación
se hace contra el mismo tramo del año anterior, no contra el año entero, así
que 2026 hasta junio se mide contra Ene-Jun de 2025.

---

## Personalizar

### Cambiar la ciudad de referencia

En `index.html`, la constante `FOCO`. En `etl.py`, `CIUDAD_FOCO`.

### Cambiar qué ciudades salen comparadas por defecto

En `index.html`, la variable `comparar`.

### Colores

Todos salen del Nexus Design System y están en un solo bloque `:root` al
comienzo de `index.html`, con el nombre de cada color de la marca. Los momentos
cromáticos por sección están en la constante `TEMAS`.

Reglas del sistema que ya vienen aplicadas: la paleta principal domina la
composición y el color temático funciona como acento; las gradaciones son
verticales con el tono oscuro en la base; los extremos de barras y líneas van
redondeados; los datos se ordenan por tamaño; y los titulares no usan
mayúsculas ni itálicas.

### Tipografía

Ver `docs/assets/fonts/LEEME.txt`.

### Morfologías

Los arcos que se ven en las cabeceras de sección y en las tarjetas están
generados por código a partir de la descripción del brandbook: aros
fragmentados en seis partes, esquinas redondeadas, composiciones de uno a tres
arcos. Están en la función `arcos()`.

Si tienes los archivos originales en SVG, se pueden reemplazar por los de la
marca y quedan idénticos al sistema.

---

## Advertencias de lectura

- Las poblaciones vienen del DANE en miles; el tablero ya las convierte a personas.
- Toda variable cuya proporción respecto a la fuerza de trabajo sea menor al
  10% tiene un error de muestreo superior al 5%, el límite de calidad que
  admite el DANE.
- Entre 2010 y 2020 la información ya incorpora los ajustes de población del
  cambio de marco de 2021.
- La serie de informalidad arranca en 2021 por el cambio metodológico de la GEIH.
- Cali A.M. incluye a Cali y Yumbo.

---

**Fuente:** DANE — Gran Encuesta Integrada de Hogares (GEIH).
**Elaboración:** Cámara de Comercio de Cali.
