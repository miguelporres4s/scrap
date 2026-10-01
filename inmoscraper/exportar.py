"""Escritura de resultados en CSV y Excel."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .modelos import COLUMNAS, NUMERICAS, Anuncio


def guardar_csv(anuncios: Iterable[Anuncio], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    # utf-8-sig para que Excel abra bien los acentos
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        for a in anuncios:
            w.writerow(a.fila())
    tmp.replace(ruta)


def leer_csv(ruta: Path) -> list[dict]:
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def consolidar(carpeta: Path) -> tuple[Path, Path | None]:
    """Une los CSV de cada zona en ``todas_las_zonas.csv`` y un Excel con una
    hoja por zona más una hoja de resumen."""
    archivos = sorted(p for p in carpeta.glob("*.csv") if not p.name.startswith("todas_las_zonas"))
    por_zona = {p.stem: leer_csv(p) for p in archivos}
    filas = [f for fs in por_zona.values() for f in fs]

    ruta_csv = carpeta / "todas_las_zonas.csv"
    with open(ruta_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)

    try:
        from openpyxl import Workbook
    except ImportError:
        return ruta_csv, None

    wb = Workbook()
    resumen = wb.active
    resumen.title = "Resumen"
    resumen.append(["zona", "pais", "portal", "anuncios", "con_precio", "precio_mediano", "moneda"])
    usados: set[str] = {"Resumen"}
    for stem, fs in por_zona.items():
        precios = sorted(float(f["precio"]) for f in fs if f.get("precio"))
        monedas = {f["moneda"] for f in fs if f.get("moneda")}
        primera = fs[0] if fs else {}
        resumen.append([
            primera.get("zona", stem), primera.get("pais", ""), primera.get("portal", ""), len(fs),
            len(precios), precios[len(precios) // 2] if precios else None,
            ", ".join(sorted(monedas)),
        ])
        nombre = _nombre_hoja(primera.get("zona") or stem, usados)
        ws = wb.create_sheet(nombre)
        ws.append(COLUMNAS)
        for f in fs:
            ws.append([_celda(c, f.get(c, "")) for c in COLUMNAS])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
    ruta_xlsx = carpeta / "todas_las_zonas.xlsx"
    wb.save(ruta_xlsx)
    return ruta_csv, ruta_xlsx


def _celda(columna: str, v):
    if v in ("", None):
        return None
    if columna in NUMERICAS:
        try:
            return float(v)
        except ValueError:
            return v
    return v


def _nombre_hoja(nombre: str, usados: set[str]) -> str:
    base = "".join(c for c in nombre if c not in r'[]:*?/\\')[:31] or "zona"
    cand, i = base, 2
    while cand in usados:
        sufijo = f" ({i})"
        cand = base[: 31 - len(sufijo)] + sufijo
        i += 1
    usados.add(cand)
    return cand
