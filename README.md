# osintkit

**osintkit** es un toolkit de **OSINT y web scraping** en Python para recolectar
**informacion publica** de forma respetuosa: respeta `robots.txt`, aplica
*rate limiting*, deduplica y exporta a JSONL/CSV/HTML.

> Uso responsable: recolecta solo datos publicos, respeta los terminos de servicio
> de cada sitio, la legislacion de proteccion de datos y el `robots.txt`. No incluye
> escaneo de puertos, fuerza bruta ni pruebas de intrusion.
>
> **Aviso legal:** los resultados pueden contener datos personales (nombres,
> telefonos, correos, identificaciones). Tratalos solo con una **base legal**
> (consentimiento, interes legitimo o fin periodistico/investigativo), conforme al
> RGPD y a la normativa local (p. ej. Ley 8968 en Costa Rica). Aplica minimizacion
> y elimina los archivos de `output/` cuando dejen de ser necesarios.

## Instalacion

El proyecto ya incluye un entorno virtual en `.venv` con todas las dependencias
base (`httpx`, `beautifulsoup4`, `dnspython`, `rich`, `PyYAML`) y Playwright con
Chromium. **Activalo antes de usar la herramienta:**

```bash
cd /home/kali/osintkit
source .venv/bin/activate    # el prompt cambia a (.venv)
```

Con el venv activo puedes usar el comando `osintkit` o `python -m osintkit`.

Si necesitas recrearlo desde cero:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .                 # dependencias base
pip install -e ".[browser]"      # opcional: navegador Playwright (busquedas fiables)
pip install -e ".[xpath]"        # opcional: soporte XPath via lxml
playwright install chromium      # descarga Chromium para el navegador
```

## Inicio rapido

La forma mas sencilla es lanzar el **menu interactivo** (sin argumentos):

```bash
cd /home/kali/osintkit
source .venv/bin/activate    # recuerda activar el venv
osintkit                     # abre el menu numerado
osintkit menu                # idem, explicito
```

El menu ofrece:
1. Buscar una persona (nombre, telefono, id, email, nickname)
2. Reconocimiento pasivo de un dominio
3. Rastrear un sitio (crawl)
4. Scrapear una URL con un YAML
5. Regenerar informe HTML desde un JSONL

Tambien puedes usar los comandos directamente:

```bash
# 0. Activar el venv
cd /home/kali/osintkit
source .venv/bin/activate

# 1. Reconocimiento pasivo de dominios (+ informe HTML)
osintkit domain ejemplo.com otro.org --report

# 2. Scraping configurable por selectores CSS/XPath
osintkit scrape examples/example_scrape.yaml --report

# 3. Rastreo acotado y respetuoso de un sitio
osintkit crawl https://ejemplo.com --depth 2 --max-pages 50 \
  --include /blog/ --exclude /login --report

# 4. Regenerar un informe desde resultados ya guardados
osintkit report output/domain_20261020-035751.jsonl --title "Mi informe"

# 5. Buscar una persona por dato (nombre, telefono, identificacion, email, @nick)
osintkit search "Juan Perez Gomez" --browser --report

# 6. Combinar varios datos con '+' (nombre + empresa/segundo dato)
osintkit search "María Fernanda Cordero Rojas+G4S" --browser --report

# 7. Ver la ayuda de cualquier comando
osintkit --help
osintkit domain --help
```

Los resultados (JSONL/CSV/HTML) se guardan en la carpeta `output/`. Para abrir un
informe: `xdg-open output/<nombre>.html`.

> La tabla de resultados en pantalla solo se muestra en una terminal con TTY; en
> entornos sin TTY los archivos de `output/` se generan igualmente.

## Uso

### 1. Scraping configurable (por selectores CSS/XPath)

```bash
osintkit scrape examples/example_scrape.yaml
```

Formato YAML:

```yaml
scrapes:
  - url: "https://sitio.com/listado"
    container: "article.item"   # bloque repetido (una fila por match)
    mode: css                    # css (default) o xpath
    fields:
      - name: titulo
        selector: "h2 a"
      - name: enlace
        selector: "h2 a"
        attr: href
      - name: etiquetas
        selector: ".tag"
        all: true                # lista con todos los matches
```

### 2. Reconocimiento pasivo de dominios

```bash
osintkit domain ejemplo.com otro.org
```

Recolecta DNS (A/AAAA, MX, NS, TXT), certificado TLS, cabeceras HTTP,
tecnologias detectadas y estado de `robots.txt`. Solo informacion publica.

### 3. Rastreo acotado

```bash
osintkit crawl https://ejemplo.com --depth 2 --max-pages 50 \
  --include /blog/ --exclude /login
```

### 4. Regenerar un informe HTML

```bash
osintkit report output/crawl_20260101-120000.jsonl --title "Rastreo ejemplo.com"
```

### 5. Buscar una persona por dato (nombre, telefono, identificacion, email o nickname)

```bash
# Deteccion automatica del tipo de dato
osintkit search "Juan Perez Gomez" --browser
osintkit search "+506 8888 9999" --browser
osintkit search "@torvalds"
osintkit search "juan@mail.com"

# Combinar varios datos con '+' (se buscan juntos y por separado)
osintkit search "María Fernanda Cordero Rojas+G4S" --browser --report

# Forzar el tipo y elegir buscadores
osintkit search "123456789" --type id
osintkit search "Juan Perez" --providers searxng,bing --browser --report
```

El comando detecta automaticamente si el dato es un **nombre**, **telefono**,
**identificacion**, **email** o **nickname**, genera variantes de consulta y
rastrea:

- Buscadores: `searxng` (default), `duckduckgo`, `bing`, `google`.
- Redes sociales publicas por nickname: GitHub, X, Instagram, Reddit, TikTok,
  Telegram, Keybase (omite el sitio si el perfil no existe).
- Registros publicos: subdominios via `crt.sh` cuando el dato es dominio/email.

**Buscador con navegador real (`--browser`).** Los buscadores HTML bloquean o
degradan las respuestas para clientes HTTP simples (DuckDuckGo responde `202`,
Bing devuelve ruido). Con `--browser` se usa **Playwright** con un Chromium real,
lo que permite consultar **SearXNG** (meta-buscador, proveedor por defecto) y
obtener resultados fiables. Requiere haber ejecutado `playwright install chromium`
(ya hecho en `.venv`). Puedes fijar instancias con la variable
`SEARXNG_INSTANCES` (separadas por coma).

Banderas:

| Bandera | Descripcion |
| --- | --- |
| `--type name,phone,id,email,username` | fuerza el tipo de dato |
| `--browser` | usa un navegador real (Playwright); activa SearXNG |
| `--headful` | muestra el navegador (solo con `--browser`) |
| `--providers searxng,duckduckgo,bing,google` | buscadores a usar (default: searxng) |
| `--per-query N` | resultados por consulta (default: 10) |
| `--no-social` | no comprobar perfiles en redes sociales |
| `--no-registries` | no consultar registros publicos (crt.sh) |
| `--no-fallback` | no reintentar con otro buscador si el principal falla |
| `--no-strict` | no filtrar resultados irrelevantes (SEO/genericos) |

Google usa la API Programmable Search; define `GOOGLE_CSE_KEY` y `GOOGLE_CSE_CX`
en el entorno para activarlo (si no estan, se omite silenciosamente).

> Algunos buscadores pueden devolver CAPTCHA o bloquear peticiones; el toolkit
> aplica pausas y reintentos, pero no evita esos controles. Usa `--delay` alto
> para no saturar. Con `--browser` la fiabilidad mejora notablemente.


## Informe HTML

Cualquiera de los comandos puede generar un informe HTML autocontenido
(sin dependencias externas, con estilos embebidos) anadiendo `--report`:

```bash
osintkit domain ejemplo.com --report
# -> output/domain_<fecha>.html
```

El informe incluye un **resumen agregado** (tarjetas con totales, graficos de
barras por estado HTTP, tecnologias y registros por dominio), la tabla de
registros, una seccion por registro y el JSON crudo plegable. Se genera junto a
los exportes JSONL/CSV.

Para regenerar un informe a partir de un JSONL ya existente:

```bash
osintkit report output/domain_20260101-120000.jsonl --title "Mi informe"
# --out ruta.html  --subtitle "texto"  --output carpeta
```

## Opciones comunes

| Opcion | Descripcion |
| --- | --- |
| `--delay 1.5` | segundos entre peticiones |
| `--timeout 20` | timeout por peticion |
| `--output carpeta` | carpeta de salida |
| `--formats jsonl,csv,json` | formatos de exportacion |
| `--report` | generar tambien un informe HTML autocontenido |
| `--no-robots` | ignorar robots.txt (requiere `--i-have-authorization`) |
| `--i-have-authorization` | confirma que tienes permiso del sitio para ignorar robots.txt |

## Estructura

```
osintkit/
  __init__.py       version del paquete
  __main__.py       entrypoint (python -m osintkit)
  config.py         ajustes y user-agent
  http.py           cliente con rate limit, reintentos y cache
  browser.py        fetcher con navegador real (Playwright) para buscadores
  storage.py        grabadora JSONL/CSV/JSON
  report.py         informe HTML autocontenido
  cli.py            interfaz de linea de comandos
  menu.py           menu interactivo numerado
  modules/
    scrape.py       scraping declarativo
    domain.py       reconocimiento pasivo
    crawl.py        rastreo acotado y respetuoso
    detect.py       deteccion automatica del tipo de dato y consultas '+'
    search.py       busqueda por nombre/telefono/id/email/nickname
```

## Seguridad y legalidad

Medidas implementadas:

- **`robots.txt` obligatorio por defecto**: el cliente HTTP comprueba `robots.txt`
  del host (con cache) antes de cada peticion en `scrape`, `domain` y `search`.
  Para ignorarlo hay que pasar `--no-robots` **y** `--i-have-authorization`.
- **Rate limiting** (`--delay`) y reintentos con backoff.
- **Proxy seguro**: se rechazan proxies `http://` salvo
  `OSINTKIT_ALLOW_INSECURE_PROXY=1`.
- **Perfiles sociales sin falsos positivos**: solo se reporta un perfil con
  evidencia positiva especifica de la plataforma (no basta un HTTP 200).
- **Identificaciones**: `--type id` avisa del riesgo y de la necesidad de base legal.
- **Sin exposición de secretos**: las API keys se leen del entorno y nunca se
  escriben en salidas; TLS se valida por defecto.
- **Aviso legal en cada informe** y `html.escape` en todo el HTML (sin XSS).

Recomendaciones de uso responsable:

- Usa `--delay` alto y limita los volumenes; no satures los sitios.
- Revisa los ToS de cada sitio e instancia de SearXNG.
- Minimiza y elimina los datos de `output/` cuando ya no los necesites.

## Roadmap

- Fuentes OSINT adicionales (RSS, sitemaps, Whois, crt.sh para subdominios).
- Enriquecimiento con `commoncrawl` / `wayback`.
- Soporte de plugins para nuevos modulos.
- Mas instancias SearXNG y proveedores con API (Brave, SerpAPI).