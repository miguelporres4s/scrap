"""Nuroa (agregador de portales inmobiliarios; Ecuador, Honduras, etc. según el país).

Búsqueda por texto libre: ``/venta/<que>-<donde>`` o ``/alquiler/<que>-<donde>`` (ej. ``/venta/bodega-via-daule``).
Paginación ``?page=N``. Al ser un agregador trae anuncios de varios portales (ver ``fuente_original`` en la
ficha) y el texto libre es ruidoso: filtra por la columna Ubicación/Tipo en Excel si hace falta. El enlace de
cada anuncio es un redireccionador de Nuroa hacia el portal original.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..modelos import Anuncio
from ..utilidades import limpiar, parse_caracteristicas, parse_float
from .base import Portal, con_parametro

_TIPOS = [("terreno", "Terreno"), ("lote", "Terreno"), ("galp", "Galpón"), ("ofibodega", "Ofibodega"),
          ("bodega", "Bodega"), ("nave", "Nave industrial"), ("oficina", "Oficina"), ("local", "Local"),
          ("departamento", "Departamento"), ("suite", "Departamento"), ("casa", "Casa"), ("villa", "Casa")]


def _operacion(titulo: str, desc: str, por_url: str) -> str:
    """Nuroa mezcla alquileres en búsquedas de venta: manda el texto del anuncio."""
    t = f"{titulo} {desc[:120]}".lower()
    if re.search(r"\b(alquil|arriend|renta)", t):
        return "renta"
    if re.search(r"\b(vend|venta)", t):
        return "venta"
    return por_url


def _tipo(texto: str) -> str:
    t = texto.lower()
    return next((v for k, v in _TIPOS if k in t), "")


class Nuroa(Portal):
    nombre = "nuroa"
    dominios = ("nuroa.com.ec", "nuroa.com.mx", "nuroa.com.pe", "nuroa.com.co", "nuroa.com.pa", "nuroa.com.do",
                "nuroa.hn", "nuroa.com.hn", "nuroa.cl", "nuroa.com.ar")
    modo_preferido = "http"
    selector_espera = "div.nu_row"
    moneda_defecto = "USD"

    def url_pagina(self, n: int) -> str:
        return con_parametro(self.url_base, "page", n if n > 1 else None)

    def total_paginas(self, soup: BeautifulSoup) -> Optional[int]:
        t = (soup.title.string or "") if soup.title else ""
        m = re.search(r"(\d[\d.]*)\s+\w+\s+en\s+(?:venta|alquiler)", t)
        return -(-int(m.group(1).replace(".", "")) // 25) if m else None

    def parsear(self, html: str, url: str) -> list[Anuncio]:
        soup = self.sopa(html)
        op = "renta" if "/alquiler/" in url else "venta" if "/venta/" in url else ""
        res = []
        for c in soup.select("div.nu_row[id^=nu_flat_]"):
            a = c.select_one("h3[itemprop=name] a, a.nu_adlink")
            if not a:
                continue
            titulo = limpiar(a.get_text(" "))
            precio_nodo = c.select_one("[itemprop=price]")
            mon_nodo = c.select_one("[itemprop=priceCurrency]")
            mapa = c.select_one(".nu_ver_mapa")
            desc = limpiar((c.select_one(".description") or c).get_text(" ")) if c.select_one(".description") else ""
            feats = [limpiar(li.get_text(" ")) for li in c.select("ul.nu_features li") if limpiar(li.get_text(" "))]
            fuente = limpiar((c.select_one(".nu_partner_footer") or c).get_text(" ")) if c.select_one(".nu_partner_footer") else ""
            actualizado = limpiar((c.select_one(".nu_desc_updated") or c).get_text(" ")) if c.select_one(".nu_desc_updated") else ""
            carac = parse_caracteristicas(feats)
            if "superficie_total_m2" not in carac and "superficie_m2" not in carac:
                m = re.search(r"([\d.,]+)\s*(?:m2|m²|mts2|metros)", f"{titulo} {desc}", re.I)
                if m:
                    carac["superficie_total_m2"] = parse_float(m.group(1).replace(".", "").replace(",", "."))
            res.append(
                Anuncio(
                    portal=self.nombre, id=c["id"].replace("nu_flat_", ""),
                    url=(a.get("href") or "").split("?")[0],
                    titulo=titulo, precio=parse_float(precio_nodo.get("content")) if precio_nodo else None,
                    moneda=(mon_nodo.get("content") if mon_nodo else "") or self.moneda_defecto,
                    precio_texto=limpiar(precio_nodo.get_text()) if precio_nodo else "",
                    operacion=_operacion(titulo, desc, op), tipo=_tipo(titulo + " " + desc[:80]),
                    ubicacion=limpiar((c.select_one(".nu_address_text") or c).get_text(" ")) if c.select_one(".nu_address_text") else "",
                    lat=parse_float(mapa.get("data-lat")) if mapa else None,
                    lon=parse_float(mapa.get("data-lon")) if mapa else None,
                    descripcion=desc[:400],
                    extra={"_ficha": {"descripcion_completa": desc, "fuente_original": fuente,
                                      "caracteristicas": ", ".join(feats), "actualizado": actualizado}},
                    **carac,
                )
            )
        return res
