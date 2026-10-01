"""Recorre todas las páginas de una zona y guarda los anuncios."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .descarga import AjustesDescarga, Bloqueado, Descargador
from .exportar import guardar_csv
from .modelos import Anuncio
from .portales import Portal, detectar
from .utilidades import slug

log = logging.getLogger(__name__)


@dataclass
class Zona:
    nombre: str
    url: str
    pais: str = ""
    portal: Optional[str] = None  # forzar adaptador (si la detección por dominio no basta)
    modo: Optional[str] = None
    max_paginas: Optional[int] = None


@dataclass
class Resultado:
    zona: str
    portal: str
    url: str
    anuncios: int = 0
    paginas: int = 0
    estado: str = "pendiente"  # ok | parcial | bloqueado | error
    detalle: str = ""
    archivo: str = ""
    inicio: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    fin: str = ""


def elegir_modo(zona: Zona, portal: Portal, modo_global: str) -> str:
    if zona.modo:
        return zona.modo
    if modo_global != "auto":
        return modo_global
    return portal.modo_preferido


def scrapear_zona(zona: Zona, desc: Descargador, carpeta: Path, *, modo_global: str = "auto",
                  max_paginas: int = 200, config_portales: Optional[dict[str, Any]] = None) -> Resultado:
    portal = detectar(zona.url, config_portales, forzar=zona.portal)
    modo = elegir_modo(zona, portal, modo_global)
    limite = zona.max_paginas or max_paginas
    archivo = carpeta / f"{slug(zona.nombre)}.csv"
    res = Resultado(zona=zona.nombre, portal=portal.nombre, url=zona.url, archivo=str(archivo))
    vistos: dict[str, Anuncio] = {}
    log.info("▶ %s | portal=%s | modo=%s", zona.nombre, portal.nombre, modo)

    n, url, total = 1, portal.url_pagina(1), None
    completo = False
    try:
        while url and n <= limite:
            html, usado = desc.obtener(url, modo, portal.selector_espera, portal.acciones_navegador())
            modo = usado  # si 'auto' cayó a navegador, nos quedamos en navegador
            anuncios = portal.parsear(html, url) if html else []
            nuevos = 0
            for a in anuncios:
                a.zona, a.pais, a.pagina = zona.nombre, zona.pais, n
                if a.clave and a.clave not in vistos:
                    vistos[a.clave] = a
                    nuevos += 1
            if n == 1 and html:
                total = portal.total_paginas(portal.sopa(html))
            res.paginas = n
            log.info("  pág %s%s: %s anuncios (%s nuevos) — acumulado %s",
                     n, f"/{total}" if total else "", len(anuncios), nuevos, len(vistos))
            guardar_csv(vistos.values(), archivo)  # checkpoint por página
            # Fin: página vacía o repetida (muchos portales devuelven la última
            # página otra vez cuando te pasas), o llegamos al total informado.
            if not anuncios or nuevos == 0 or (total and n >= total):
                completo = True
                break
            n += 1
            url = portal.url_siguiente(html, url, n)
        completo = completo or not url
        res.estado = "ok" if completo else "parcial"
        if not completo:
            res.detalle = f"se alcanzó max_paginas={limite}"
    except Bloqueado as e:
        res.estado, res.detalle = ("parcial" if vistos else "bloqueado"), str(e)
        log.error("  ✖ bloqueado: %s", e)
    except Exception as e:  # noqa: BLE001 - una zona caída no debe frenar las demás
        res.estado, res.detalle = ("parcial" if vistos else "error"), f"{type(e).__name__}: {e}"
        log.exception("  ✖ error en %s", zona.nombre)

    if vistos:
        guardar_csv(vistos.values(), archivo)
    res.anuncios = len(vistos)
    res.fin = datetime.now().isoformat(timespec="seconds")
    log.info("■ %s: %s anuncios en %s páginas [%s]", zona.nombre, res.anuncios, res.paginas, res.estado)
    return res


def scrapear_zonas(zonas: list[Zona], ajustes: AjustesDescarga, carpeta: Path, *,
                   max_paginas: int = 200, config_portales: Optional[dict[str, Any]] = None,
                   reanudar: bool = False) -> list[Resultado]:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_resumen = carpeta / "resumen.json"
    previos: dict[str, dict] = {}
    if reanudar and ruta_resumen.exists():
        previos = {r["zona"]: r for r in json.loads(ruta_resumen.read_text(encoding="utf-8"))}

    resultados: dict[str, Resultado] = {k: Resultado(**v) for k, v in previos.items()}
    with Descargador(ajustes) as desc:
        for i, zona in enumerate(zonas, 1):
            if previos.get(zona.nombre, {}).get("estado") == "ok":
                log.info("(%s/%s) %s ya está completa, la salto", i, len(zonas), zona.nombre)
                continue
            log.info("(%s/%s)", i, len(zonas))
            resultados[zona.nombre] = scrapear_zona(
                zona, desc, carpeta, modo_global=ajustes.modo, max_paginas=max_paginas,
                config_portales=config_portales,
            )
            ruta_resumen.write_text(
                json.dumps([asdict(r) for r in resultados.values()], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    return list(resultados.values())
