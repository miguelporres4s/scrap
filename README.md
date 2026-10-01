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

## Proyectos (hoja "Proyectos Entregar"): un Excel por proyecto, cada zona se descarga una sola vez

`proyectos.yaml` contiene los proyectos de la hoja **ya sin repetidos** (p. ej. Cap Cana y Costa Pacífica
aparecían 2 veces; MILEX y ARTEC comparten Torreón; SMA lo usan 2 proyectos). Las descargas se identifican
por URL: si dos proyectos o zonas comparten una fuente, se baja **una vez** y el Excel de cada proyecto
replica esa información.

```bash
python -m inmoscraper proyectos --plan                  # qué se va a bajar, sin descargar (79 descargas distintas)
python -m inmoscraper proyectos --pais PA --pais RD     # primero Panamá y República Dominicana
python -m inmoscraper proyectos                         # todo, ordenado por prioridad
python -m inmoscraper proyectos --fichas                # + ficha de detalle de cada anuncio (lento; se reanuda)
python -m inmoscraper proyectos --fichas --max-fichas 500
python -m inmoscraper proyectos --solo-excel            # regenera los Excel con lo ya descargado
```

Resultado en `resultados/proyectos/`:

| archivo | contenido |
|---|---|
| `00_indice_proyectos.xlsx` | hoja *Proyectos* (anuncios por proyecto) y *Zonas únicas* (qué se descargó una vez y qué proyectos lo usan) |
| `<folio>_<proyecto>.xlsx` | *Resumen* (alcance, fuentes, estado de cada una), *Lista de precios* (precio, m², **precio por m²**, recámaras…), *Hoteles* (Booking) y *Ficha completa* |

La hoja *Resumen* marca en **rojo** una fuente que falló/bloqueó y en **amarillo** una con 0 anuncios o URL
"por verificar": un Excel vacío casi siempre significa bloqueo, no que no haya inventario.
Se puede interrumpir y relanzar: continúa donde se quedó (`datos/estado.json`, `datos/fichas.jsonl`).

### Portales por país

| país | vivienda | hoteles |
|---|---|---|
| **Panamá** | `icasas.com.pa` (verificado: apartamentos, casas, lotes-terrenos, residenciales/proyectos, alquiler) + Mercado Libre Panamá | Booking |
| **Rep. Dominicana** | Mercado Libre RD + **SuperCasas** (adaptador verificado; pega el link con el sector elegido) | Booking |
| **México** | `icasas.mx` (verificado) + Mercado Libre México | Booking |

`icasas` **no opera en República Dominicana ni en Perú** y no tiene categoría de lotes/terrenos en México
(sí en Panamá). Airbnb no se toca.

### Fuentes verificadas para Panamá y República Dominicana

| fuente | país | qué trae |
|---|---|---|
| `icasas.com.pa` | PA | apartamentos, casas, lotes, proyectos (residenciales), venta y alquiler |
| `inmopanama.com` | PA | oferta de inmobiliarias por zona (usa `?sort=newest` para una paginación estable). **Ojo**: `/costa-pacifica` de este sitio es una torre de Punta Pacífica, no el proyecto de Veracruz |
| `gruposucasa.com` | PA | lista de precios del **desarrollador** (modelo, áreas, precio desde, letra quincenal, ingreso requerido, bono) del proyecto Costa Pacífica y de PH Mar Pacífico / Verde Mar 2 |
| `rentahouserd.com` (EasyBroker) | RD | todo lo que está en venta por sector (`ln=ID`); Cap Cana = `ln=87257`. El mismo adaptador sirve para casaspb, miscasasrd, rdcondominio, puntacanasolutions, inmobiliarianaco |
| `supercasas.com` | RD | adaptador listo; pega el link del buscador con el sector elegido |

La columna **Alerta** del Excel marca (sin borrar) precios o precios por m² atípicos que suelen ser errores de quien publica.

Fichas en paralelo (una terminal por portal, ahorra tiempo):

```bash
python -m inmoscraper proyectos --pais PA --pais RD --fichas --fichas-portal rentahouserd
python -m inmoscraper proyectos --pais PA --pais RD --fichas --fichas-portal icasas-pa
python -m inmoscraper proyectos --pais PA --pais RD --fichas --fichas-portal inmopanama
python -m inmoscraper proyectos --pais PA --pais RD --solo-excel     # al final, arma los Excel con todo
```

### Mercado Libre y Booking: correr en tu equipo

Ambos bloquean IP de servidores (Mercado Libre redirige a `/gz/account-verification`, Booking a un desafío).
En tu PC normalmente funcionan: el modo `auto` prueba HTTP y, si hay verificación, abre Chrome (ventana
visible; si pide captcha lo resuelves una vez y se guarda en `.perfil_navegador/`).
Las URLs de Mercado Libre del YAML llevan `verificar: true` porque no pude abrirlas desde el entorno de
desarrollo; si una trae 0 anuncios, abre el link en el navegador, ajústalo a la URL real de la búsqueda y relanza.
Mercado Libre corta cada búsqueda en ~2,000 resultados (42 páginas): si una zona lo alcanza, divídela por tipo o
por rango de precio con varias fuentes.

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
| **icasas** | MX, PA | http | verificado contra el sitio real (icasas.mx e icasas.com.pa) |
| **SuperCasas** | RD | http | verificado contra el sitio real |
| **Mercado Libre** | MX, PA, DO, AR, CO, CL, PE... | auto | **sin verificar** (bloqueado desde el servidor de desarrollo); usar `probar` |
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
