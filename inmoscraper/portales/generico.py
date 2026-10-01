"""Adaptador genérico para portales sin adaptador propio.

Dos niveles:
1. **Configurado** en ``portales.yaml`` con selectores CSS (sin programar).
2. **Automático**: lee datos estructurados (JSON-LD / microdatos schema.org)
   que publican muchos portales, y busca el enlace "siguiente" para paginar.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from bs4 import BeautifulSoup, Tag

from ..modelos import Anuncio
from ..utilidades import limpiar, parse_caracteristicas, parse_float, parse_precio
from .base import Portal, con_parametro

_TIPOS_SCHEMA = {
    "residence", "apartment", "house", "singlefamilyresidence", "accommodation",
    "realestatelisting", "offer", "product", "place", "hotel", "lodgingbusiness",
    "apartmentcomplex", "room", "suite", "vacationrental",
}
_TEXTOS_SIGUIENTE = re.compile(r"^(siguiente|próxima|proxima|next|sig\.?|›|»|>)$", re.I)


class Generico(Portal):
    nombre = "generico"

    def __init__(self, url_base: str, config: Optional[dict[str, Any]] = None, nombre: str = ""):
        super().__init__(url_base)
        self.config = config or {}
        if nombre:
            self.nombre = nombre
        self.modo_preferido = self.config.get("modo", "auto")
        self.moneda_defecto = self.config.get("moneda", "")
        self.selector_espera = self.config.get("tarjeta")

    # ------------------------------------------------------------ paginación
    def url_pagina(self, n: int) -> str:
        pag = self.config.get("paginacion") or {}
        if n == 1:
            return self.url_base
        if pag.get("parametro"):
            inicio = pag.get("inicio", 1)
            paso = pag.get("paso", 1)
            return con_parametro(self.url_base, pag["parametro"], inicio + (n - 1) * paso)
        if pag.get("ruta"):
            return pag["ruta"].format(base=self.url_base.rstrip("/"), n=n)
        return ""  # se usa url_siguiente()

    def url_siguiente(self, html: str, url_actual: str, n: int) -> Optional[str]:
        url = self.url_pagina(n)
        if url:
            return url
        soup = self.sopa(html)
        sel = (self.config.get("paginacion") or {}).get("siguiente")
        if sel:
            return self.absoluta(_extraer(soup, sel), url_actual) or None
        nodo = soup.select_one("a[rel~=next], link[rel~=next]")
        if nodo is None:
            nodo = next((a for a in soup.select("a[href]") if _TEXTOS_SIGUIENTE.match(limpiar(a.get_text())
                                                                                       or a.get("aria-label", ""))), None)
        return self.absoluta(nodo.get("href"), url_actual) if nodo else None

    # --------------------------------------------------------------- parseo
    def parsear(self, html: str, url: str) -> list[Anuncio]:
        soup = self.sopa(html)
        if self.config.get("tarjeta"):
            return self._por_selectores(soup, url)
        return self._jsonld(soup, url) or self._microdatos(soup, url)

    def _por_selectores(self, soup: BeautifulSoup, url: str) -> list[Anuncio]:
        campos: dict[str, str] = self.config.get("campos", {})
        res = []
        for card in soup.select(self.config["tarjeta"]):
            v = {k: _extraer(card, sel) for k, sel in campos.items() if k != "caracteristicas"}
            feats = [limpiar(x.get_text(" ")) for x in card.select(campos["caracteristicas"])] \
                if campos.get("caracteristicas") else []
            precio, moneda = parse_precio(v.get("precio"), self.moneda_defecto)
            enlace = self.absoluta(v.pop("url", "") or "", url)
            carac = parse_caracteristicas(feats)
            for k in ("superficie_m2", "recamaras", "banos", "estacionamientos"):
                if v.get(k):
                    carac[k] = parse_precio(v.pop(k))[0]
                v.pop(k, None)
            ident = _extraer(card, self.config["id"]) if self.config.get("id") else ""
            res.append(
                Anuncio(
                    portal=self.nombre,
                    url=enlace,
                    id=ident or "",
                    titulo=v.get("titulo", ""),
                    precio=precio,
                    moneda=moneda,
                    precio_texto=v.get("precio", ""),
                    direccion=v.get("direccion", ""),
                    ubicacion=v.get("ubicacion", ""),
                    descripcion=v.get("descripcion", ""),
                    anunciante=v.get("anunciante", ""),
                    tipo=v.get("tipo", ""),
                    operacion=self.config.get("operacion", ""),
                    extra={"caracteristicas": feats} if feats else {},
                    **carac,
                )
            )
        return res

    def _jsonld(self, soup: BeautifulSoup, url: str) -> list[Anuncio]:
        nodos: list[dict] = []
        for s in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(s.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            _recolectar(data, nodos)
        res, vistos = [], set()
        for n in nodos:
            enlace = self.absoluta(n.get("url") or n.get("@id"), url)
            if not enlace or enlace in vistos:
                continue
            vistos.add(enlace)
            oferta = n.get("offers") or {}
            if isinstance(oferta, list):
                oferta = oferta[0] if oferta else {}
            precio_raw = n.get("price") or oferta.get("price") or (oferta.get("priceSpecification") or {}).get("price")
            moneda = n.get("priceCurrency") or oferta.get("priceCurrency") or self.moneda_defecto
            dir_ = n.get("address") or {}
            geo = n.get("geo") or {}
            area = n.get("floorSize") or {}
            res.append(
                Anuncio(
                    portal=self.nombre,
                    url=enlace,
                    titulo=limpiar(str(n.get("name", ""))),
                    precio=parse_precio(str(precio_raw))[0] if precio_raw is not None else None,
                    moneda=str(moneda),
                    precio_texto=str(precio_raw or ""),
                    descripcion=limpiar(str(n.get("description", "")))[:500],
                    direccion=limpiar(dir_.get("streetAddress", "")) if isinstance(dir_, dict) else limpiar(str(dir_)),
                    ubicacion=limpiar(dir_.get("addressLocality", "")) if isinstance(dir_, dict) else "",
                    lat=parse_float(geo.get("latitude")) if isinstance(geo, dict) else None,
                    lon=parse_float(geo.get("longitude")) if isinstance(geo, dict) else None,
                    superficie_m2=parse_float(area.get("value")) if isinstance(area, dict) else None,
                    recamaras=parse_float(n.get("numberOfBedrooms") or n.get("numberOfRooms")),
                    banos=parse_float(n.get("numberOfBathroomsTotal")),
                    tipo=str(n.get("@type", "")),
                )
            )
        return res

    def _microdatos(self, soup: BeautifulSoup, url: str) -> list[Anuncio]:
        res = []
        for el in soup.select("[itemscope][itemtype]"):
            tipo = el.get("itemtype", "").rstrip("/").split("/")[-1]
            if tipo.lower() not in _TIPOS_SCHEMA:
                continue
            u = el.select_one("[itemprop=url]")
            enlace = self.absoluta((u.get("href") or u.get("content")) if u else "", url)
            if not enlace:
                continue
            nombre = el.select_one("[itemprop=name]")
            precio_nodo = el.select_one("[itemprop=price]")
            precio_txt = (precio_nodo.get("content") or precio_nodo.get_text(" ")) if precio_nodo else ""
            precio, moneda = parse_precio(precio_txt, self.moneda_defecto)
            res.append(
                Anuncio(
                    portal=self.nombre, url=enlace, id=el.get("id", ""),
                    titulo=limpiar((nombre.get("content") or nombre.get_text(" ")) if nombre else ""),
                    precio=precio, moneda=moneda, precio_texto=limpiar(precio_txt),
                    ubicacion=self.meta(el, "addressLocality"),
                    lat=parse_float(self.meta(el, "latitude")),
                    lon=parse_float(self.meta(el, "longitude")),
                    tipo=tipo,
                )
            )
        return res


def _extraer(nodo: Tag, selector: str) -> str:
    """Selector con atributo opcional: ``"a.titulo@href"``, ``"@data-id"`` (del propio nodo)."""
    sel, _, attr = selector.partition("@")
    objetivo = nodo.select_one(sel) if sel.strip() else nodo
    if objetivo is None:
        return ""
    if attr:
        return limpiar(objetivo.get(attr, ""))
    return limpiar(objetivo.get_text(" "))


def _recolectar(data: Any, salida: list[dict]) -> None:
    if isinstance(data, list):
        for d in data:
            _recolectar(d, salida)
        return
    if not isinstance(data, dict):
        return
    tipo = data.get("@type")
    tipos = [t.lower() for t in (tipo if isinstance(tipo, list) else [tipo]) if isinstance(t, str)]
    if any(t in _TIPOS_SCHEMA for t in tipos) and (data.get("url") or data.get("@id")):
        salida.append(data)
        return
    for clave in ("@graph", "itemListElement", "item", "mainEntity", "containsPlace"):
        if clave in data:
            _recolectar(data[clave], salida)
