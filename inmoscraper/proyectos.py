"""Catálogo de proyectos -> scrapeo de cada zona UNA sola vez -> Excel por proyecto.

Un proyecto (o varios folios repetidos) apunta a una o más *zonas* por clave.
Cada zona tiene *fuentes* (portal + link, o parámetros de icasas). Si dos
proyectos comparten una zona, la zona se scrapea una vez y su información se
replica en el Excel de cada proyecto.
"""
from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from .descarga import AjustesDescarga, Bloqueado, Descargador
from .ejecutor import Resultado, Zona, scrapear_zona
from .exportar import leer_csv
from .portales import detectar
from .portales.icasas import url_icasas, url_icasas_pa
from .utilidades import slug

log = logging.getLogger(__name__)


# ----------------------------------------------------------------- catálogo
@dataclass
class Unidad:
    """Una URL concreta a scrapear (una fuente de una zona)."""
    id: str
    zona: str
    portal: str
    url: str
    etiqueta: str
    pais: str
    operacion: str = ""
    tipo: str = ""
    max_paginas: Optional[int] = None
    verificar: bool = False  # URL no comprobada contra el sitio real


@dataclass
class Proyecto:
    folios: list[str]
    nombre: str
    pais: str = ""
    prioridad: int = 5
    responsable: str = ""
    alcance: str = ""
    notas: str = ""
    zonas: list[str] = field(default_factory=list)

    @property
    def archivo(self) -> str:
        return f"{self.folios[0]}_{slug(self.nombre)}.xlsx"


@dataclass
class Catalogo:
    ajustes: dict[str, Any]
    zonas: dict[str, dict[str, Any]]
    proyectos: list[Proyecto]

    def unidades(self, clave: str) -> list[Unidad]:
        z = self.zonas[clave]
        res: list[Unidad] = []
        for f in z.get("fuentes", []):
            portal = f["portal"]
            etiqueta = f.get("etiqueta", "")
            comunes = dict(zona=clave, portal=portal, pais=z.get("pais", ""),
                           max_paginas=f.get("max_paginas"), verificar=bool(f.get("verificar")))
            if portal == "icasas" and "url" not in f:
                for op in f.get("operaciones", ["venta"]):
                    for tipo in f["tipos"]:
                        if "lugar" in f:  # icasas.com.pa
                            url = url_icasas_pa(op, tipo, f["lugar"])
                            uid = f"icasas-pa__{op}-{tipo}-{f['lugar']}"
                        else:  # icasas.mx
                            url = url_icasas(op, tipo, f["estado"], f["municipio"])
                            uid = f"icasas__{op}-{tipo}-{f['estado']}-{f['municipio']}"
                        res.append(Unidad(id=uid, url=url, etiqueta=f"icasas {op} {tipo}",
                                          operacion=op, tipo=tipo, **comunes))
            else:
                etiqueta = etiqueta or slug(f["url"].split("//")[-1])[:40]
                res.append(Unidad(id=f"{portal}__{slug(f['url'].split('//')[-1])[:90]}", url=f["url"],
                                  etiqueta=f"{portal} {etiqueta}", operacion=f.get("operacion", ""),
                                  tipo=f.get("tipo", ""), **comunes))
        return res


def cargar_catalogo(ruta: str | Path) -> Catalogo:
    with open(ruta, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    proyectos = [Proyecto(**p) for p in cfg.get("proyectos", [])]
    zonas = cfg.get("zonas", {})
    for p in proyectos:
        for z in p.zonas:
            if z not in zonas:
                raise ValueError(f"El proyecto '{p.nombre}' usa la zona '{z}' que no está definida en 'zonas'")
    return Catalogo(ajustes=cfg.get("ajustes", {}) or {}, zonas=zonas, proyectos=proyectos)


def seleccionar(cat: Catalogo, paises: Optional[list[str]] = None, solo: Optional[list[str]] = None,
                ) -> list[Proyecto]:
    sel = sorted(cat.proyectos, key=lambda p: (p.prioridad, p.folios[0]))
    if paises:
        paises = [x.upper() for x in paises]
        sel = [p for p in sel if p.pais.upper() in paises]
    if solo:
        f = [s.lower() for s in solo]
        sel = [p for p in sel if any(x in p.nombre.lower() or any(x in fo.lower() for fo in p.folios) for x in f)]
    return sel


def zonas_unicas(proyectos: list[Proyecto]) -> dict[str, list[Proyecto]]:
    """clave de zona -> proyectos que la usan (en orden de prioridad)."""
    res: dict[str, list[Proyecto]] = {}
    for p in proyectos:
        for z in p.zonas:
            res.setdefault(z, []).append(p)
    return res


# ----------------------------------------------------------------- ejecución
class Estado:
    """Persistencia mínima para poder reanudar: datos/estado.json."""

    def __init__(self, carpeta: Path):
        self.ruta = carpeta / "estado.json"
        self.datos: dict[str, dict] = json.loads(self.ruta.read_text(encoding="utf-8")) if self.ruta.exists() else {}

    def guardar(self, u: Unidad, r: Resultado) -> None:
        self.datos[u.id] = {**asdict(r), "unidad": asdict(u)}
        self.ruta.write_text(json.dumps(self.datos, ensure_ascii=False, indent=1), encoding="utf-8")

    def ok(self, uid: str) -> bool:
        return self.datos.get(uid, {}).get("estado") == "ok"


def ruta_unidad(carpeta: Path, u: Unidad) -> Path:
    return carpeta / "unidades" / f"{slug(u.id)}.csv"


def ejecutar_listados(cat: Catalogo, proyectos: list[Proyecto], ajustes: AjustesDescarga, carpeta: Path,
                      *, reanudar: bool = True, max_paginas: int = 200,
                      config_portales: Optional[dict] = None, desc: Optional[Descargador] = None) -> Estado:
    carpeta.mkdir(parents=True, exist_ok=True)
    estado = Estado(carpeta)
    unicas = zonas_unicas(proyectos)
    unidades, vistas = [], set()
    for clave in unicas:  # la misma URL en dos zonas se descarga una sola vez
        for u in cat.unidades(clave):
            if u.id not in vistas:
                vistas.add(u.id)
                unidades.append(u)
    log.info("%s proyectos -> %s zonas únicas -> %s fuentes a scrapear", len(proyectos), len(unicas), len(unidades))
    propio = desc is None
    desc = desc or Descargador(ajustes)
    try:
        for i, u in enumerate(unidades, 1):
            if reanudar and estado.ok(u.id):
                log.info("(%s/%s) %s ya está completa, la salto", i, len(unidades), u.id)
                continue
            log.info("(%s/%s) %s%s", i, len(unidades), u.id, "  [URL por verificar]" if u.verificar else "")
            z = Zona(nombre=u.id, url=u.url, pais=u.pais, max_paginas=u.max_paginas)
            r = scrapear_zona(z, desc, carpeta / "unidades", modo_global=ajustes.modo,
                              max_paginas=max_paginas, config_portales=config_portales)
            if r.anuncios == 0 and r.estado == "ok":
                r.detalle = r.detalle or "0 anuncios (zona sin inventario en ese filtro, o URL/selectores por revisar)"
            estado.guardar(u, r)
    finally:
        if propio:
            desc.cerrar()
    return estado


# -------------------------------------------------------------------- fichas
class CacheFichas:
    """datos/fichas.jsonl: una línea por URL ya descargada (permite reanudar)."""

    def __init__(self, carpeta: Path):
        self.ruta = carpeta / "fichas.jsonl"
        self.datos: dict[str, dict] = {}
        if self.ruta.exists():
            for linea in self.ruta.read_text(encoding="utf-8").splitlines():
                try:
                    d = json.loads(linea)
                    self.datos[d["url"]] = d["ficha"]
                except (json.JSONDecodeError, KeyError):
                    continue

    def agregar(self, url: str, ficha: dict) -> None:
        self.datos[url] = ficha
        with open(self.ruta, "a", encoding="utf-8") as f:
            f.write(json.dumps({"url": url, "ficha": ficha}, ensure_ascii=False) + "\n")


def ejecutar_fichas(cat: Catalogo, proyectos: list[Proyecto], ajustes: AjustesDescarga, carpeta: Path,
                    *, max_fichas: Optional[int] = None, config_portales: Optional[dict] = None,
                    desc: Optional[Descargador] = None) -> CacheFichas:
    cache = CacheFichas(carpeta)
    urls: list[tuple[str, str]] = []
    vistas: set[str] = set()
    for clave in zonas_unicas(proyectos):
        for u in cat.unidades(clave):
            if u.portal == "booking":
                continue  # hoteles: la ficha de Booking ya viene en el listado
            ruta = ruta_unidad(carpeta, u)
            if not ruta.exists():
                continue
            for fila in leer_csv(ruta):
                if fila["url"] and fila["url"] not in vistas and fila["url"] not in cache.datos:
                    vistas.add(fila["url"])
                    urls.append((u.id, fila["url"]))
    if max_fichas is not None:
        urls = urls[:max_fichas]
    log.info("%s fichas por descargar (%s ya en caché)", len(urls), len(cache.datos))
    propio = desc is None
    desc = desc or Descargador(ajustes)
    seguidos = 0
    try:
        for i, (uid, url) in enumerate(urls, 1):
            portal = detectar(url, config_portales)
            modo = ajustes.modo if ajustes.modo != "auto" else portal.modo_preferido
            try:
                html, _ = desc.obtener(url, modo, portal.selector_ficha)
                if html:
                    cache.agregar(url, portal.parsear_ficha(html, url))
                seguidos = 0
            except Bloqueado as e:
                seguidos += 1
                log.error("ficha bloqueada (%s seguidas): %s", seguidos, e)
                if seguidos >= 3:
                    log.error("Demasiados bloqueos seguidos; detengo las fichas (se puede reanudar).")
                    break
            except Exception as e:  # noqa: BLE001
                log.warning("ficha %s falló: %s", url, e)
            if i % 25 == 0:
                log.info("  fichas %s/%s", i, len(urls))
    finally:
        if propio:
            desc.cerrar()
    return cache


# --------------------------------------------------------------- lectura datos
def filas_unidad(carpeta: Path, u: Unidad) -> list[dict]:
    ruta = ruta_unidad(carpeta, u)
    if not ruta.exists():
        return []
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))
