# osintkit

**osintkit** is an **OSINT and web scraping** toolkit in Python for collecting **public information** responsibly: it respects `robots.txt`, applies rate limiting, deduplicates results, and exports to JSONL/CSV/HTML.

> Responsible use: only collect public data, respect each site's terms of service, data protection laws, and `robots.txt`. It does not include port scanning, brute force, or intrusion testing.
>
> **Legal notice:** results may contain personal data (names, phone numbers, emails, IDs). Only process them with a **legal basis** (consent, legitimate interest, or journalistic/investigative purpose), in compliance with GDPR and local regulations (e.g. Costa Rica's Law 8968). Apply data minimization and delete files in `output/` when no longer needed.

## Installation

The project includes a virtual environment in `.venv` with base dependencies (`httpx`, `beautifulsoup4`, `dnspython`, `rich`, `PyYAML`) and Playwright with Chromium. **Activate it before using the tool:**

```bash
cd /home/orami/desarrollo_web/osintkit
source .venv/bin/activate    # prompt changes to (.venv)
```

With the venv active, you can use `osintkit` or `python -m osintkit`.

If you need to recreate it from scratch:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .                 # base dependencies
pip install -e ".[browser]"      # optional: Playwright browser (more reliable searches)
pip install -e ".[xpath]"        # optional: XPath support via lxml
playwright install chromium      # download Chromium for the browser
```

## Quick start

The easiest way is to launch the **interactive menu** (no arguments):

```bash
cd /home/orami/desarrollo_web/osintkit
source .venv/bin/activate
osintkit                     # opens numbered menu
osintkit menu                # same, explicit
```

The menu offers:
1. Search for a person (name, phone, ID, email, nickname)
2. Passive reconnaissance of a domain
3. Crawl a site
4. Scrape a URL with a YAML config
5. Regenerate HTML report from JSONL

You can also use commands directly:

```bash
# 0. Activate venv
cd /home/orami/desarrollo_web/osintkit
source .venv/bin/activate

# 1. Passive domain reconnaissance (+ HTML report)
osintkit domain example.com another.org --report

# 2. Configurable scraping via CSS/XPath selectors
osintkit scrape examples/example_scrape.yaml --report

# 3. Respectful, scoped site crawl
osintkit crawl https://example.com --depth 2 --max-pages 50 \
  --include /blog/ --exclude /login --report

# 4. Regenerate report from saved results
osintkit report output/domain_20261020-035751.jsonl --title "My report"

# 5. Search for a person by data (name, phone, ID, email, @nick)
osintkit search "John Doe" --browser --report

# 6. Combine multiple data points with '+' (name + company/second data)
osintkit search "John Doe+Acme" --browser --report

# 7. View help for any command
osintkit --help
osintkit domain --help
```

Results (JSONL/CSV/HTML) are saved in the `output/` folder. To open a report: `xdg-open output/<name>.html`.

> The results table on screen is only shown in a TTY terminal; in non-TTY environments, files in `output/` are still generated.

## Usage

### 1. Configurable scraping (CSS/XPath selectors)

```bash
osintkit scrape examples/example_scrape.yaml
```

YAML format:

```yaml
scrapes:
  - url: "https://site.com/list"
    container: "article.item"   # repeated block (one row per match)
    mode: css                    # css (default) or xpath
    fields:
      - name: title
        selector: "h2 a"
      - name: link
        selector: "h2 a"
        attr: href
      - name: tags
        selector: ".tag"
        all: true                # list of all matches
```
