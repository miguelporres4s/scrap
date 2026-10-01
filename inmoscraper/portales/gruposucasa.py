"""Grupo Sucasa (Panamá): lista de precios de cada proyecto/preventa.

Cada página ``/proyectos/<sector>/<proyecto>/`` publica los modelos con recámaras,
baños, áreas, precio desde, letra quincenal, ingreso requerido y bonos. Una fila
por modelo. Es la lista de precios *del desarrollador* (no es oferta de portal).
"""
from __future__ import annotations

import re

from ..modelos import Anuncio
from ..utilidades import limpiar, parse_numero
from .base import Portal

_BLOQUE = re.compile(r"(Casas|Apartamentos)\s+en\s+(.+?)\s+Modelo\s+(.+?)\s+(?=(?:Un|El|Tu|Una|La|Este|Esta|Con)\b)", re.S)
_N = r"([\d,.]+)"


def _campo(texto: str, patron: str) -> str:
    m = re.search(patron, texto, re.I)
    return m.group(1) if m else ""


class GrupoSucasa(Portal):
    nombre = "gruposucasa"
    dominios = ("gruposucasa.com",)
    modo_preferido = "http"
    selector_espera = "body"
    moneda_defecto = "USD"

    def url_pagina(self, n: int) -> str:
        return self.url_base if n == 1 else ""

    def parsear(self, html: str, url: str) -> list[Anuncio]:
        soup = self.sopa(html)
        for t in soup.select("script,style,noscript"):
            t.decompose()
        titulo_pag = limpiar(soup.title.string) if soup.title and soup.title.string else ""
        proyecto_pag = titulo_pag.split(" - ")[-1] if " - " in titulo_pag else url.rstrip("/").split("/")[-1]
        # Marca cada encabezado "Modelo X" para partir el texto en bloques
        for h in soup.select("h2.elementor-heading-title, h2, h3"):
            t = limpiar(h.get_text(" "))
            if re.fullmatch(r"Modelo\s+[\wáéíóúÁÉÍÓÚñ ]{1,30}", t):
                h.string = f" §§{t[7:].strip()}§§ "
        texto = limpiar(soup.get_text(" "))
        estado = _campo(texto, r"ESTADO\s+(Preventa|Entrega inmediata|En construcci[óo]n|\w+)")
        sector = _campo(texto, r"SECTOR\s+((?:Panamá )?\w+)")
        direccion = _campo(texto, r"DIRECCI[ÓO]N\s+(.+?)(?:\s+(?:Club|Garita|\d+ parques|Gimnasio|Piscina|Cotiza|Áreas?|Parques)\b)")
        tipo_pag = _campo(texto, r"TIPO\s+(Casas?\s+y\s+Apartamentos?|Casas?|Apartamentos?)")
        partes = re.split(r"§§(.+?)§§", texto)
        res = []
        for i in range(1, len(partes) - 1, 2):
            modelo, b = partes[i].strip(), partes[i + 1]
            previo = partes[i - 1][-140:]
            g = re.search(r"(Casas|Apartamentos)\s+en\s+((?:PH\s+)?[^§]{3,60}?)\s*$", previo)
            tipo = (g.group(1) if g else tipo_pag.split(" y ")[0] or "Casas")
            tipo = "Casa" if tipo.startswith("Casa") else "Apartamento"
            ph = g.group(2).strip() if g else proyecto_pag
            precio = parse_numero(_campo(b, rf"\$\s*{_N}\s+Precio desde"))
            letra = parse_numero(_campo(b, rf"\$\s*{_N}\s+Letra quincenal"))
            ingreso = parse_numero(_campo(b, rf"\$\s*{_N}\s+Ingreso desde"))
            tot = parse_numero(_campo(b, rf"[ÁA]REA TOTAL\s*{_N}"))
            cer = parse_numero(_campo(b, rf"CERRADA\s*{_N}")) or parse_numero(_campo(b, rf"[ÁA]REA\s*{_N}\s*m"))
            lote = parse_numero(_campo(b, rf"LOTE\s*{_N}"))
            res.append(
                Anuncio(
                    portal=self.nombre, id=f"{url.rstrip('/').split('/')[-1]}:{modelo}".replace(" ", ""),
                    url=url, titulo=f"{tipo} Modelo {modelo} - {ph}",
                    precio=precio, moneda="USD", precio_texto=f"desde ${precio:,.0f}" if precio else "",
                    operacion="venta", tipo=tipo,
                    superficie_m2=cer, superficie_total_m2=lote or tot,
                    recamaras=parse_numero(_campo(b, r"REC[ÁA]MARAS\s+(\d+)")),
                    banos=parse_numero(_campo(b, rf"BA[ÑN]O\s+{_N}")),
                    estacionamientos=parse_numero(_campo(b, r"ESTACIONAMIENTOS?(?: TECHADOS)?\s+(\d+)")),
                    ubicacion=f"{direccion}, {sector}".strip(", "), anunciante="Grupo Sucasa (desarrollador)",
                    descripcion=f"Proyecto: {ph}. Estado: {estado}.",
                    extra={"proyecto": ph, "estado_proyecto": estado, "area_total_m2": tot, "lote_m2": lote,
                           "deposito": parse_numero(_campo(b, r"DEPOSITO\s+(\d+)")),
                           "letra_quincenal_desde": letra, "ingreso_requerido_desde": ingreso,
                           "bono_lanzamiento": _campo(b, r"Recibe un Bono de (.*?)(?: por lanzamiento| TOUR| PLANO)")},
                )
            )
        return res
