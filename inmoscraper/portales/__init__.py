"""Registro de portales y detección por dominio."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import yaml

from .airbnb import Airbnb
from .base import Portal
from .booking import Booking
from .easybroker import EasyBroker
from .generico import Generico
from .gruposucasa import GrupoSucasa
from .icasas import Icasas
from .infocasas import InfoCasas
from .inmopanama import InmoPanama
from .mercadolibre import MercadoLibre
from .navent import Navent
from .nuroa import Nuroa
from .supercasas import SuperCasas

ADAPTADORES: list[type[Portal]] = [Airbnb, Nuroa, Icasas, InfoCasas, MercadoLibre, SuperCasas, EasyBroker, GrupoSucasa, InmoPanama, Navent, Booking]


def cargar_config_portales(ruta: Optional[str | Path]) -> dict[str, dict[str, Any]]:
    if not ruta or not Path(ruta).exists():
        return {}
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def detectar(url: str, config_portales: Optional[dict[str, dict]] = None,
             forzar: Optional[str] = None) -> Portal:
    """Devuelve el adaptador adecuado para ``url``.

    Prioridad: ``forzar`` (nombre) > portales.yaml > adaptadores propios > genérico.
    """
    config_portales = config_portales or {}
    host = (urlparse(url).hostname or "").lower()

    if forzar:
        if forzar in config_portales:
            return Generico(url, config_portales[forzar], nombre=forzar)
        for cls in ADAPTADORES:
            if cls.nombre == forzar or forzar in [d.split(".")[0] for d in cls.dominios]:
                return cls(url)
        if forzar == "generico":
            return Generico(url)
        raise ValueError(f"Portal desconocido: {forzar}")

    for nombre, cfg in config_portales.items():
        if any(host == d or host.endswith("." + d) for d in cfg.get("dominios", [])):
            return Generico(url, cfg, nombre=nombre)
    for cls in ADAPTADORES:
        if cls.acepta(url):
            return cls(url)
    return Generico(url, nombre=host.removeprefix("www.").split(".")[0] or "generico")


def soportados(config_portales: Optional[dict[str, dict]] = None) -> list[tuple[str, str, str]]:
    filas = [(cls.nombre, ", ".join(cls.dominios), cls.modo_preferido) for cls in ADAPTADORES]
    for nombre, cfg in (config_portales or {}).items():
        filas.append((nombre, ", ".join(cfg.get("dominios", [])), cfg.get("modo", "auto") + " (yaml)"))
    filas.append(("generico", "cualquier otro (JSON-LD / microdatos)", "auto"))
    return filas
