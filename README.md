# inmoscraper

Scraper de inventario inmobiliario **por zona** y **multi-portal**. Le das el
link del listado de una zona (tal como lo ves en el navegador, con tus filtros
aplicados), recorre todas las páginas y te deja un CSV por zona más un Excel
consolidado.

```
zonas.yaml (28 links)  ─►  detecta portal por dominio  ─►  pagina 1..N  ─►  CSV por zona
                                                                      └─►  todas_las_zonas.xlsx
```

## Instalación

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium        # solo si vas a usar portales con anti-bot
```

## Uso rápido

```bash
# 1) Probar un link: descarga solo la página 1 y muestra lo que detecta
python -m inmoscraper probar "https://www.icasas.mx/renta/habitacionales-departamentos-distrito-federal-benito-juarez-2_3_1_0_266_0"

# 2) Scrapear un link suelto completo
python -m inmoscraper url "<link>" --zona "CDMX Benito Juárez" --pais MX

# 3) Scrapear todas tus zonas
python -m inmoscraper zonas zonas.yaml
python -m inmoscraper zonas zonas.yaml --solo tulum --solo palermo   # solo algunas
python -m inmoscraper zonas zonas.yaml --reanudar                    # continuar si se cortó

# Ver portales soportados
python -m inmoscraper portales
```

Los resultados quedan en `resultados/AAAA-MM-DD/`:

| archivo | contenido |
|---|---|
| `<zona>.csv` | anuncios de esa zona (se guarda tras cada página, no se pierde nada si se corta) |
| `todas_las_zonas.csv` | todo junto |
| `todas_las_zonas.xlsx` | hoja *Resumen* (anuncios, precio mediano por zona) + una hoja por zona |
| `resumen.json` | estado de cada zona (`ok`, `parcial`, `bloqueado`, `error`) |

## Dar de alta tus 28 zonas

Edita `zonas.yaml`. Por cada zona: entra al portal, filtra (operación, tipo,
zona, precio…), copia el link de la página de resultados y pégalo:

```yaml
zonas:
  - nombre: MX - Tulum - casas venta
    pais: MX
    url: https://www.inmuebles24.com/casas-en-venta-en-tulum.html
  - nombre: AR - Palermo - deptos venta
    pais: AR
    url: https://www.zonaprop.com.ar/departamentos-venta-palermo.html
```

Cambiar de zona o de portal = cambiar el link. Antes de lanzar las 28, usa
`probar` con cada link nuevo para confirmar que se leen bien los anuncios.

## Portales

| portal | países | modo | estado |
|---|---|---|---|
| **icasas** | MX | http | verificado contra el sitio real |
| **Navent**: inmuebles24, zonaprop, imovelweb, urbania, adondevivir, plusvalia, compreoalquile | MX, AR, BR, PE, EC, PA | navegador | probado con HTML de ejemplo; **verificar con `probar`** |
| **booking.com** | todos | navegador | probado con HTML de ejemplo; **verificar con `probar`** |
| **genérico** | cualquiera | auto | lee JSON-LD / microdatos schema.org y sigue el enlace "siguiente" |
| **portales.yaml** | cualquiera | configurable | defines selectores CSS sin programar |

Modos de descarga:

- `http`: rápido, para portales sin protección.
- `navegador`: abre Chromium/Chrome con Playwright. Necesario para portales con
  Cloudflare (inmuebles24, zonaprop…) o que cargan con JavaScript (Booking).
  Con `headless: false` verás la ventana; si aparece un captcha, resuélvelo y
  el scraper continúa. Las cookies se guardan en `.perfil_navegador/`, así que
  normalmente solo hay que hacerlo una vez.
- `auto`: cada portal usa su modo preferido; si un portal HTTP empieza a
  bloquear, se cambia solo a navegador.

### Anti-bot: recomendaciones

- Corre desde tu PC / red de oficina (las IP de servidores en la nube suelen
  estar bloqueadas por Cloudflare).
- Usa `canal: chrome` (tu Google Chrome instalado) y `headless: false`.
- Deja pausas de 2–5 s entre páginas (`pausa` en `zonas.yaml`).
- Si un portal te bloquea seguido, se puede añadir un proxy residencial en
  `ajustes.proxy`.

### Agregar un portal nuevo

1. **Sin código**: `python -m inmoscraper probar "<link>" --guardar-html p.html`,
   abre `p.html` (o *Inspeccionar* en el navegador), y define la tarjeta y
   campos en `portales.yaml` (hay una plantilla comentada).
2. **Con código** (para portales complejos): crea una clase en
   `inmoscraper/portales/` que herede de `Portal` e implemente `url_pagina()` y
   `parsear()`, y regístrala en `portales/__init__.py`.

> **Booking.com no es un portal inmobiliario**: lista alojamientos (hoteles,
> rentas vacacionales). Sirve para medir oferta de hospedaje en la zona; incluye
> `checkin`/`checkout` en el link para que muestre precios.

## Columnas

`portal, url, id, titulo, precio, moneda, precio_texto, expensas, operacion,
tipo, superficie_m2, superficie_total_m2, recamaras, banos, estacionamientos,
direccion, ubicacion, lat, lon, anunciante, calificacion, descripcion, extra,
zona, pais, pagina, fecha_scrape`

Los anuncios se deduplican dentro de cada zona por `id` (o URL). La corrida de
una zona termina cuando una página no trae anuncios nuevos, se llega al total
de páginas que informa el portal, o a `max_paginas`.

## Tests

```bash
pip install pytest
python -m pytest
```

## Uso responsable

Revisa los términos de uso y el `robots.txt` de cada portal, no bajes la pausa
entre páginas y usa los datos para análisis interno. Los datos de contacto de
anunciantes no se extraen.
