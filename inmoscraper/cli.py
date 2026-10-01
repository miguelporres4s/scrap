"""Línea de comandos.

Ejemplos::

    python -m inmoscraper probar "https://www.icasas.mx/venta/..."
    python -m inmoscraper url "https://www.icasas.mx/venta/..." --zona "Benito Juárez"
    python -m inmoscraper zonas zonas.yaml
    python -m inmoscraper zonas zonas.yaml --solo tulum --solo cancun
    python -m inmoscraper consolidar resultados/2026-10-01
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .descarga import AjustesDescarga, Descargador
from .ejecutor import Zona, scrapear_zonas
from .exportar import consolidar
from .portales import cargar_config_portales, detectar, soportados
from . import proyectos as pr

RAIZ = Path.cwd()


def _ajustes(base: dict[str, Any], args: argparse.Namespace) -> AjustesDescarga:
    nav = base.get("navegador", {}) or {}
    a = AjustesDescarga(
        modo=base.get("modo", "auto"),
        pausa=tuple(base.get("pausa", (2, 5))),
        reintentos=base.get("reintentos", 3),
        timeout=base.get("timeout", 40),
        idioma=base.get("idioma", AjustesDescarga.idioma),
        headless=nav.get("headless", False),
        canal=nav.get("canal"),
        ejecutable=nav.get("ejecutable"),
        perfil=nav.get("perfil", ".perfil_navegador"),
        espera_desafio=nav.get("espera_desafio", 90),
        proxy=base.get("proxy"),
    )
    if args.modo:
        a.modo = args.modo
    if args.headless is not None:
        a.headless = args.headless
    if getattr(args, "canal", None):
        a.canal = args.canal
    return a


def _leer_yaml(ruta: str) -> dict[str, Any]:
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _carpeta(salida: str) -> Path:
    return Path(salida) / date.today().isoformat()


def cmd_zonas(args) -> int:
    cfg = _leer_yaml(args.archivo)
    base = cfg.get("ajustes", {}) or {}
    zonas = [Zona(**z) for z in cfg.get("zonas", [])]
    if args.solo:
        filtros = [s.lower() for s in args.solo]
        zonas = [z for z in zonas if any(f in z.nombre.lower() for f in filtros)]
    if not zonas:
        print("No hay zonas que scrapear (revisa el archivo o --solo).", file=sys.stderr)
        return 1
    carpeta = Path(args.carpeta) if args.carpeta else _carpeta(args.salida or base.get("salida", "resultados"))
    portales = cargar_config_portales(args.portales)
    resultados = scrapear_zonas(
        zonas, _ajustes(base, args), carpeta,
        max_paginas=args.max_paginas or base.get("max_paginas", 200),
        config_portales=portales, reanudar=args.reanudar,
    )
    return _cerrar(carpeta, resultados)


def cmd_url(args) -> int:
    zona = Zona(nombre=args.zona or "zona", url=args.link, pais=args.pais or "", portal=args.portal)
    carpeta = Path(args.carpeta) if args.carpeta else _carpeta(args.salida or "resultados")
    resultados = scrapear_zonas(
        [zona], _ajustes({}, args), carpeta, max_paginas=args.max_paginas or 200,
        config_portales=cargar_config_portales(args.portales),
    )
    return _cerrar(carpeta, resultados)


def _cerrar(carpeta: Path, resultados) -> int:
    csv_, xlsx = consolidar(carpeta)
    print("\nResumen")
    print(f"{'zona':40} {'portal':14} {'anuncios':>8} {'págs':>5}  estado")
    for r in resultados:
        print(f"{r.zona[:40]:40} {r.portal[:14]:14} {r.anuncios:>8} {r.paginas:>5}  {r.estado} {r.detalle}")
    print(f"\nArchivos en {carpeta}/  ->  {csv_.name}" + (f", {xlsx.name}" if xlsx else ""))
    return 0 if all(r.estado == "ok" for r in resultados) else 2


def cmd_probar(args) -> int:
    """Descarga solo la primera página y muestra qué se detecta: útil para
    dar de alta una zona o un portal nuevo antes de lanzar todo."""
    portales = cargar_config_portales(args.portales)
    portal = detectar(args.link, portales, forzar=args.portal)
    ajustes = _ajustes({}, args)
    modo = ajustes.modo if ajustes.modo != "auto" else portal.modo_preferido
    with Descargador(ajustes) as d:
        url = portal.url_pagina(1)
        html, usado = d.obtener(url, modo, portal.selector_espera, portal.acciones_navegador())
    anuncios = portal.parsear(html, url) if html else []
    print(f"Portal detectado : {portal.nombre}  (modo {usado})")
    print(f"Anuncios en pág 1: {len(anuncios)}")
    print(f"Total de páginas : {portal.total_paginas(portal.sopa(html)) if html else None}")
    print(f"Página 2         : {portal.url_siguiente(html, url, 2) if html else None}")
    for a in anuncios[: args.n]:
        print(f"  - {a.titulo[:60]!r} | {a.precio} {a.moneda} | {a.superficie_m2} m2 | "
              f"{a.recamaras} rec | {a.ubicacion[:40]} | {a.url}")
    if args.guardar_html:
        Path(args.guardar_html).write_text(html, encoding="utf-8")
        print(f"HTML guardado en {args.guardar_html}")
    if not anuncios:
        print("\nNo se encontraron anuncios. Opciones: probar --modo navegador --visible, o "
              "definir el portal en portales.yaml (guarda el HTML con --guardar-html para ver selectores).")
        return 1
    return 0


def cmd_proyectos(args) -> int:
    """Catálogo de proyectos: scrapea cada zona única una vez y genera un Excel por proyecto."""
    from .excel_proyectos import escribir_excels

    cat = pr.cargar_catalogo(args.archivo)
    sel = pr.seleccionar(cat, [x for v in (args.pais or []) for x in v.split(",")], args.solo)
    if not sel:
        print("Ningún proyecto coincide con los filtros.", file=sys.stderr)
        return 1
    ajustes = _ajustes(cat.ajustes, args)
    base = Path(args.datos or cat.ajustes.get("datos", "datos"))
    salida = Path(args.salida or cat.ajustes.get("salida", "resultados")) / "proyectos"
    portales = cargar_config_portales(args.portales)
    unicas = pr.zonas_unicas(sel)
    print(f"{len(sel)} proyectos -> {len(unicas)} zonas únicas (cada una se scrapea una sola vez)")
    if args.plan:
        usos: dict[str, tuple] = {}
        for clave, ps in unicas.items():
            for u in cat.unidades(clave):
                usos.setdefault(u.id, (u, set()))[1].update(p.folios[0] for p in ps)
        for uid, (u, folios) in usos.items():
            print(f"  {uid[:70]:70} {'[verificar]' if u.verificar else '':12} {', '.join(sorted(folios))}")
        print(f"\n{len(usos)} descargas distintas")
        return 0
    with Descargador(ajustes) as desc:
        if not args.solo_excel:
            pr.ejecutar_listados(cat, sel, ajustes, base, reanudar=not args.rehacer,
                                 max_paginas=args.max_paginas or cat.ajustes.get("max_paginas", 200),
                                 config_portales=portales, desc=desc)
            if args.fichas:
                pr.ejecutar_fichas(cat, sel, ajustes, base, max_fichas=args.max_fichas,
                                   config_portales=portales, desc=desc, solo_portal=args.fichas_portal)
    archivos = escribir_excels(cat, sel, base, salida)
    est = pr.Estado(base)
    print("\nEstado de las fuentes")
    mostradas = set()
    for clave in unicas:
        for u in cat.unidades(clave):
            if u.id in mostradas:
                continue
            mostradas.add(u.id)
            e = est.datos.get(u.id, {})
            print(f"  {u.id[:62]:62} {e.get('anuncios', 0):>6} anuncios  {e.get('estado', 'sin ejecutar'):12} {e.get('detalle', '')[:50]}")
    print(f"\nExcel generados en {salida}/:")
    for a in archivos:
        print("  ", a.name)
    return 0


def cmd_portales(args) -> int:
    for nombre, dominios, modo in soportados(cargar_config_portales(args.portales)):
        print(f"{nombre:16} {modo:18} {dominios}")
    return 0


def cmd_consolidar(args) -> int:
    csv_, xlsx = consolidar(Path(args.carpeta))
    print(csv_, xlsx or "")
    return 0


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="inmoscraper", description="Scraper de inventario inmobiliario por zona")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def comunes(sp, con_salida=True):
        sp.add_argument("--modo", choices=["auto", "http", "navegador"])
        g = sp.add_mutually_exclusive_group()
        g.add_argument("--visible", dest="headless", action="store_false", default=None,
                       help="abre la ventana del navegador (recomendado con Cloudflare)")
        g.add_argument("--oculto", dest="headless", action="store_true", help="navegador headless")
        sp.add_argument("--canal", help="'chrome' para usar el Google Chrome instalado")
        sp.add_argument("--portal", help="forzar adaptador (ver comando 'portales')")
        sp.add_argument("--portales", default=str(RAIZ / "portales.yaml"), help="config de portales extra")
        if con_salida:
            sp.add_argument("--max-paginas", type=int)
            sp.add_argument("--salida", help="carpeta base de resultados (default: resultados)")
            sp.add_argument("--carpeta", help="carpeta exacta de salida (en vez de salida/fecha)")

    z = sub.add_parser("zonas", help="scrapea todas las zonas de un YAML")
    z.add_argument("archivo", nargs="?", default="zonas.yaml")
    z.add_argument("--solo", action="append", help="solo zonas cuyo nombre contenga este texto (repetible)")
    z.add_argument("--reanudar", action="store_true", help="salta zonas ya completas en la carpeta")
    comunes(z)
    z.set_defaults(func=cmd_zonas)

    u = sub.add_parser("url", help="scrapea un link suelto")
    u.add_argument("link")
    u.add_argument("--zona")
    u.add_argument("--pais")
    comunes(u)
    u.set_defaults(func=cmd_url)

    t = sub.add_parser("probar", help="prueba la primera página de un link")
    t.add_argument("link")
    t.add_argument("-n", type=int, default=5, help="anuncios a mostrar")
    t.add_argument("--guardar-html")
    comunes(t, con_salida=False)
    t.set_defaults(func=cmd_probar)

    pj = sub.add_parser("proyectos", help="catálogo de proyectos: una zona = una sola descarga, un Excel por proyecto")
    pj.add_argument("archivo", nargs="?", default="proyectos.yaml")
    pj.add_argument("--pais", action="append", help="solo estos países, p. ej. --pais PA --pais RD (o PA,RD)")
    pj.add_argument("--solo", action="append", help="solo proyectos cuyo nombre/folio contenga este texto")
    pj.add_argument("--plan", action="store_true", help="solo muestra qué se va a scrapear, sin descargar")
    pj.add_argument("--fichas", action="store_true", help="además descarga la ficha de detalle de cada anuncio (lento)")
    pj.add_argument("--fichas-portal", help="solo fichas de las fuentes cuyo id empiece así (p. ej. icasas-pa, rentahouserd); "
                                            "permite correr varios portales en paralelo en terminales distintas")
    pj.add_argument("--max-fichas", type=int, help="tope de fichas por corrida (se reanuda con la caché)")
    pj.add_argument("--solo-excel", action="store_true", help="no descarga nada, regenera los Excel con lo ya descargado")
    pj.add_argument("--rehacer", action="store_true", help="vuelve a scrapear fuentes ya completas")
    pj.add_argument("--datos", help="carpeta de datos intermedios (default: datos)")
    comunes(pj)
    pj.set_defaults(func=cmd_proyectos)

    ps = sub.add_parser("portales", help="lista portales soportados")
    ps.add_argument("--portales", default=str(RAIZ / "portales.yaml"))
    ps.set_defaults(func=cmd_portales)

    c = sub.add_parser("consolidar", help="une los CSV de una carpeta en CSV + Excel")
    c.add_argument("carpeta")
    c.set_defaults(func=cmd_consolidar)
    return p


def main(argv=None) -> int:
    args = construir_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S",
    )
    return args.func(args)
