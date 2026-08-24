#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verificacion del Observatorio de Mercado Laboral
================================================

Red de seguridad del proyecto. Comprueba que los datos generados por el ETL
siguen cumpliendo las decisiones metodologicas que costaron trabajo tomar.

Uso:
    python etl.py && python verificar.py

Devuelve codigo 0 si todo pasa, 1 si algo se rompio. Pensado para correr
tambien en CI, despues de cada actualizacion mensual.

Si una prueba falla, NO la ajustes para que pase. Cada una defiende una
decision explicada en CLAUDE.md. Si el DANE cambio algo de verdad, primero
entiende que cambio y luego actualiza la prueba a conciencia.
"""

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DATOS = RAIZ / "docs" / "datos.json"

fallos = []
avisos = []


def check(nombre, condicion, detalle=""):
    if condicion:
        print(f"  ok    {nombre}")
    else:
        print(f"  FALLA {nombre}" + (f" -> {detalle}" if detalle else ""))
        fallos.append(nombre)


def aviso(nombre, detalle):
    print(f"  aviso {nombre} -> {detalle}")
    avisos.append(nombre)


def main():
    if not DATOS.exists():
        sys.exit("[ERROR] No existe docs/datos.json. Ejecuta antes: python etl.py")

    d = json.loads(DATOS.read_text(encoding="utf-8"))
    tm, an = d["periodos"]["tm"], d["periodos"]["an"]
    gen_tm = d["series"]["tm"]["general"]["Cali A.M."]
    gen_an = d["series"]["an"]["general"]["Cali A.M."]

    # ── 1. Estructura de la serie ────────────────────────────────────
    print("\n1. Estructura de las series")
    check("la serie de trimestres arranca en Ene-Mar 2007",
          tm["codigos"][0] == "2007-03", tm["codigos"][0])
    check("los trimestres moviles son consecutivos, uno por mes",
          all(
              (int(b[:4]) * 12 + int(b[5:])) - (int(a[:4]) * 12 + int(a[5:])) == 1
              for a, b in zip(tm["codigos"], tm["codigos"][1:])
          ))
    for modulo in ("general", "hombres", "mujeres", "juventud", "informalidad"):
        series = d["series"]["tm"][modulo]["Cali A.M."]
        largos = {len(s) for s in series.values()}
        check(f"{modulo}: todas las series miden lo mismo que la grilla",
              largos == {len(tm["codigos"])}, f"largos {largos}")

    # ── 2. Ceros del DANE tratados como dato faltante ────────────────
    print("\n2. Un cero exacto del DANE no es un dato")
    print("   (la subocupacion no se midio entre marzo y septiembre de 2020)")
    ceros = {
        f"{mod}.{k}": sum(1 for v in s if v == 0)
        for mod in d["series"]["tm"]
        for ciudad in d["series"]["tm"][mod]
        for k, s in d["series"]["tm"][mod][ciudad].items()
        if any(v == 0 for v in s)
    }
    check("ninguna serie contiene ceros exactos", not ceros, str(list(ceros)[:5]))

    i2020 = [tm["codigos"].index(f"2020-{m:02d}") for m in (3, 6, 9)]
    check("la subocupacion de 2020 queda vacia, no en cero",
          all(gen_tm["ts"][i] is None for i in i2020),
          str([gen_tm["ts"][i] for i in i2020]))
    check("el desempleo de 2020 si tiene dato",
          all(gen_tm["td"][i] is not None for i in i2020))

    # ── 3. Promedio anual: cuatro trimestres que no se traslapan ─────
    print("\n3. Promedio anual = Ene-Mar, Abr-Jun, Jul-Sep y Oct-Dic")
    i25 = an["codigos"].index("2025")
    cierres = [tm["codigos"].index(f"2025-{m:02d}") for m in (3, 6, 9, 12)]

    oc = sum(gen_tm["ocupados"][i] for i in cierres) / 4
    ft = sum(gen_tm["ft"][i] for i in cierres) / 4
    td_esperada = (ft - oc) / ft * 100

    check("los niveles se promedian sobre los cuatro trimestres de cierre",
          abs(gen_an["ocupados"][i25] - oc) < 0.05,
          f"{gen_an['ocupados'][i25]} vs {oc:.2f}")
    check("las tasas se recalculan desde los niveles, no se promedian",
          abs(gen_an["td"][i25] - td_esperada) < 0.02,
          f"{gen_an['td'][i25]} vs {td_esperada:.2f}")

    # El promedio de las tasas da otro numero: si coincidiera, algo se rompio
    td_promediada = sum(gen_tm["td"][i] for i in cierres) / 4
    check("el resultado NO coincide con promediar tasas",
          abs(gen_an["td"][i25] - td_promediada) > 0.005,
          "se esta promediando tasas en vez de recalcularlas")

    # ── 4. Contraste con la cifra publicada por el DANE ──────────────
    print("\n4. Contraste con lo que publica el DANE para 2025")
    check("desempleo de Cali A.M. en 2025 cerca de 8,746%",
          abs(gen_an["td"][i25] - 8.746) < 0.05, str(gen_an["td"][i25]))
    check("ocupados de Cali A.M. en 2025 cerca de 1.115.100",
          abs(gen_an["ocupados"][i25] - 1115.1) < 1.5, str(gen_an["ocupados"][i25]))

    # ── 5. Anio incompleto ───────────────────────────────────────────
    print("\n5. Un anio a medias no se compara contra uno entero")
    parciales = d["meta"].get("anios_parciales", [])
    if parciales:
        ip = an["codigos"].index(str(parciales[-1]))
        n = an["trimestres"][ip]
        check("el anio en curso queda marcado en la etiqueta",
              "(" in an["etiquetas"][ip], an["etiquetas"][ip])
        check("su referencia es el mismo tramo del anio anterior",
              an["referencia"][ip] and "(" in an["referencia"][ip],
              str(an["referencia"][ip]))
        ref = d["referencia_anual"]["general"]["Cali A.M."]["td"][ip]
        prev = [tm["codigos"].index(f"{parciales[-1]-1}-{m:02d}")
                for m in (3, 6, 9, 12)[:n]]
        oc_r = sum(gen_tm["ocupados"][i] for i in prev) / n
        ft_r = sum(gen_tm["ft"][i] for i in prev) / n
        check("la referencia usa solo los trimestres equivalentes",
              abs(ref - (ft_r - oc_r) / ft_r * 100) < 0.02,
              f"{ref} vs {(ft_r-oc_r)/ft_r*100:.2f}")
    else:
        aviso("no hay anios parciales", "no se pudo probar la comparacion equivalente")

    check("un anio completo con trimestres faltantes queda vacio",
          gen_an["ts"][an["codigos"].index("2020")] is None,
          "2020 no tiene los cuatro trimestres de subocupacion")

    # ── 6. Cobertura ─────────────────────────────────────────────────
    print("\n6. Cobertura")
    check("Cali A.M. esta en los cuatro modulos",
          all("Cali A.M." in d["series"]["tm"][m]
              for m in ("general", "hombres", "mujeres", "juventud", "informalidad")))
    check("hay al menos 23 ciudades", len(d["ciudades"]) >= 23, str(len(d["ciudades"])))
    inf = d["series"]["tm"]["informalidad"]["Cali A.M."]["prop_informalidad"]
    i2020_dic = tm["codigos"].index("2020-12")
    check("la informalidad no existe antes de 2021",
          all(v is None for v in inf[:i2020_dic + 1]))
    check("la informalidad si existe en el ultimo trimestre", inf[-1] is not None)

    # ── 7. Rangos plausibles ─────────────────────────────────────────
    print("\n7. Los numeros caen donde deben")
    for k, lo, hi in (("td", 3, 40), ("to", 30, 75), ("tgp", 45, 80),
                      ("pct_pet", 60, 90)):
        vals = [v for v in gen_tm[k] if v is not None]
        check(f"{k} entre {lo} y {hi}",
              vals and min(vals) >= lo and max(vals) <= hi,
              f"min {min(vals):.1f} max {max(vals):.1f}" if vals else "sin datos")
    ult = gen_tm["td"][-1]
    check("el ultimo trimestre trae dato de Cali", ult is not None)
    if len(gen_tm["td"]) > 13 and gen_tm["td"][-13] is not None:
        salto = abs(ult - gen_tm["td"][-13])
        if salto > 5:
            aviso("salto grande frente al mismo trimestre del anio pasado",
                  f"{salto:.1f} pp; revisa que los anexos sean los correctos")

    # ── Cierre ───────────────────────────────────────────────────────
    print("\n" + "=" * 62)
    print(f"Ultimo trimestre movil : {d['meta']['ultimo_tm']}")
    print(f"Ultimo anio            : {d['meta']['ultimo_anio']}")
    print(f"Ciudades               : {len(d['ciudades'])}")
    if avisos:
        print(f"Avisos                 : {len(avisos)}")
    if fallos:
        print(f"\nFALLARON {len(fallos)} prueba(s):")
        for f in fallos:
            print(f"  - {f}")
        print("\nNo publiques hasta resolverlo. Lee CLAUDE.md antes de tocar el ETL.")
        return 1
    print("\nTodo en orden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
