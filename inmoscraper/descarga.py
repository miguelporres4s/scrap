"""Descarga de páginas: HTTP simple o navegador real (Playwright).

- ``http``: rápido, sirve para portales sin anti-bot (p. ej. icasas).
- ``navegador``: Chromium vía Playwright, para portales con Cloudflare/WAF
  o que renderizan con JavaScript (inmuebles24, zonaprop, booking...).
- ``auto``: intenta HTTP y, si detecta bloqueo, cambia a navegador para el
  resto de la zona.
"""
from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import requests

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

_SENALES_BLOQUEO = (
    "attention required! | cloudflare",
    "just a moment...",
    "cf-chl-",
    "challenge-platform",
    "awswaf",
    "captcha-delivery",
    "px-captcha",
    "are you a robot",
    "<title>access denied</title>",
)


class Bloqueado(Exception):
    """El portal devolvió una página de desafío / anti-bot."""


def parece_bloqueo(status: int, html: str) -> bool:
    if status in (202, 403, 429, 503):
        return True
    cabeza = html[:5000].lower()
    return any(s in cabeza for s in _SENALES_BLOQUEO)


@dataclass
class AjustesDescarga:
    modo: str = "auto"  # auto | http | navegador
    pausa: tuple[float, float] = (2.0, 5.0)
    reintentos: int = 3
    timeout: float = 40.0
    idioma: str = "es-MX,es;q=0.9,en;q=0.8"
    headless: bool = False
    canal: Optional[str] = None  # "chrome" usa el Chrome instalado (mejor contra Cloudflare)
    ejecutable: Optional[str] = None
    perfil: str = ".perfil_navegador"
    espera_desafio: int = 90  # segundos para resolver un captcha a mano en modo visible
    proxy: Optional[str] = None
    extra_headers: dict[str, str] = field(default_factory=dict)


Accion = Callable[["object"], None]  # recibe un playwright Page


class Descargador:
    def __init__(self, ajustes: AjustesDescarga):
        self.a = ajustes
        self._sesion = requests.Session()
        self._sesion.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": ajustes.idioma,
                **ajustes.extra_headers,
            }
        )
        if ajustes.proxy:
            self._sesion.proxies = {"http": ajustes.proxy, "https": ajustes.proxy}
        self._pw = None
        self._contexto = None
        self._pagina = None
        self._ultima = 0.0

    # ------------------------------------------------------------------ util
    def _pausar(self) -> None:
        espera = random.uniform(*self.a.pausa) - (time.monotonic() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        self._ultima = time.monotonic()

    def cerrar(self) -> None:
        if self._contexto is not None:
            try:
                self._contexto.close()
            except Exception:  # pragma: no cover - cierre best effort
                pass
        if self._pw is not None:
            self._pw.stop()
        self._pw = self._contexto = self._pagina = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cerrar()

    # ------------------------------------------------------------------ http
    def http(self, url: str) -> str:
        ultimo_error: Optional[Exception] = None
        for intento in range(1, self.a.reintentos + 1):
            self._pausar()
            try:
                r = self._sesion.get(url, timeout=self.a.timeout)
            except requests.RequestException as e:
                ultimo_error = e
                log.warning("Error de red (%s/%s) %s: %s", intento, self.a.reintentos, url, e)
                time.sleep(2**intento)
                continue
            r.encoding = r.encoding or r.apparent_encoding
            if parece_bloqueo(r.status_code, r.text):
                raise Bloqueado(f"HTTP {r.status_code} en {url}")
            if r.status_code == 404:
                return ""
            if r.status_code >= 500:
                ultimo_error = RuntimeError(f"HTTP {r.status_code}")
                time.sleep(2**intento)
                continue
            r.raise_for_status()
            return r.text
        raise RuntimeError(f"No se pudo descargar {url}: {ultimo_error}")

    # ------------------------------------------------------------- navegador
    def _abrir_navegador(self):
        if self._pagina is not None:
            return self._pagina
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "Falta Playwright: pip install playwright && playwright install chromium"
            ) from e
        self._pw = sync_playwright().start()
        opciones = dict(
            headless=self.a.headless,
            locale=self.a.idioma.split(",")[0],
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        ejecutable = self.a.ejecutable or os.environ.get("INMOSCRAPER_CHROMIUM")
        if ejecutable:
            opciones["executable_path"] = ejecutable
        elif self.a.canal:
            opciones["channel"] = self.a.canal
        if self.a.proxy:
            opciones["proxy"] = {"server": self.a.proxy}
        # Contexto persistente: las cookies de un desafío resuelto se conservan
        # entre ejecuciones, así no hay que resolverlo cada vez.
        Path(self.a.perfil).mkdir(parents=True, exist_ok=True)
        self._contexto = self._pw.chromium.launch_persistent_context(self.a.perfil, **opciones)
        self._contexto.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self._pagina = self._contexto.pages[0] if self._contexto.pages else self._contexto.new_page()
        return self._pagina

    def navegador(self, url: str, esperar_selector: Optional[str] = None,
                  acciones: Optional[Accion] = None) -> str:
        pagina = self._abrir_navegador()
        ultimo_error: Optional[Exception] = None
        for intento in range(1, self.a.reintentos + 1):
            self._pausar()
            try:
                resp = pagina.goto(url, wait_until="domcontentloaded", timeout=self.a.timeout * 1000)
                status = resp.status if resp else 200
                html = pagina.content()
                if parece_bloqueo(status, html):
                    html = self._esperar_desafio(pagina)
                if esperar_selector:
                    try:
                        pagina.wait_for_selector(esperar_selector, timeout=15000)
                    except Exception:
                        log.info("No apareció '%s' en %s (¿página vacía?)", esperar_selector, url)
                else:
                    pagina.wait_for_timeout(1500)
                if acciones:
                    acciones(pagina)
                return pagina.content()
            except Bloqueado:
                raise
            except Exception as e:
                ultimo_error = e
                log.warning("Error en navegador (%s/%s) %s: %s", intento, self.a.reintentos, url, e)
                time.sleep(2**intento)
        raise RuntimeError(f"No se pudo descargar {url}: {ultimo_error}")

    def _esperar_desafio(self, pagina) -> str:
        """Espera a que el desafío anti-bot se resuelva (solo o a mano)."""
        limite = time.monotonic() + (self.a.espera_desafio if not self.a.headless else 20)
        if not self.a.headless:
            log.warning(
                "Desafío anti-bot detectado. Si ves un captcha en la ventana, resuélvelo "
                "(espero %ss)...", self.a.espera_desafio,
            )
        while time.monotonic() < limite:
            pagina.wait_for_timeout(2000)
            html = pagina.content()
            if not parece_bloqueo(200, html):
                return html
        raise Bloqueado(f"Sigue bloqueado tras esperar: {pagina.url}")

    # --------------------------------------------------------------- general
    def obtener(self, url: str, modo: str, esperar_selector: Optional[str] = None,
                acciones: Optional[Accion] = None) -> tuple[str, str]:
        """Devuelve (html, modo_usado). En modo auto cae a navegador si hay bloqueo."""
        if modo == "http":
            return self.http(url), "http"
        if modo == "navegador":
            return self.navegador(url, esperar_selector, acciones), "navegador"
        try:
            return self.http(url), "http"
        except Bloqueado as e:
            log.info("%s -> cambio a modo navegador", e)
            return self.navegador(url, esperar_selector, acciones), "navegador"
