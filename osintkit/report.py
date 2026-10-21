"""Generacion de informes HTML autocontenidos, legibles para humanos."""

from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone
from typing import Any, Iterable

CSS = """
:root { --bg:#0f172a; --card:#1e293b; --fg:#e2e8f0; --muted:#94a3b8; --accent:#38bdf8;
        --border:#334155; --ok:#4ade80; --warn:#fbbf24; --err:#f87171; --link:#7dd3fc; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
       font:15px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
header { padding:32px 40px; border-bottom:1px solid var(--border); background:#111a2e; }
header h1 { margin:0 0 6px; font-size:26px; letter-spacing:-.01em; }
header .meta { color:var(--muted); font-size:13px; }
main { padding:28px 40px; max-width:1100px; margin:0 auto; }
section { margin-bottom:36px; }
h2 { font-size:17px; color:var(--accent); border-bottom:1px solid var(--border);
     padding-bottom:8px; margin:0 0 16px; }
h3 { font-size:14px; color:var(--muted); text-transform:uppercase; letter-spacing:.05em;
     margin:20px 0 10px; }
a { color:var(--link); text-decoration:none; word-break:break-all; }
a:hover { text-decoration:underline; }
code { background:#0b1220; padding:1px 6px; border-radius:4px; font-size:13px; }
.badge { display:inline-block; padding:2px 10px; border-radius:999px; background:#0b1220;
         border:1px solid var(--border); font-size:12px; }
details { background:var(--card); border:1px solid var(--border); border-radius:8px;
          padding:10px 14px; margin-top:10px; }
summary { cursor:pointer; color:var(--muted); }
pre { overflow:auto; background:#0b1220; padding:14px; border-radius:8px; font-size:12px;
      max-height:520px; }
footer { padding:20px 40px; color:var(--muted); font-size:12px; border-top:1px solid var(--border);
         max-width:1100px; margin:0 auto; line-height:1.7; }
footer p { margin:6px 0; }
.empty { color:var(--muted); font-style:italic; }

/* Tarjetas de resumen */
.cards { display:flex; flex-wrap:wrap; gap:14px; }
.card { background:var(--card); border:1px solid var(--border); border-radius:10px;
        padding:14px 20px; min-width:130px; }
.card .num { font-size:26px; font-weight:700; color:var(--accent); }
.card .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }

/* Tabla resumen (indice de registros) */
table { width:100%; border-collapse:collapse; background:var(--card); border-radius:10px;
        overflow:hidden; }
th, td { text-align:left; padding:10px 12px; border-bottom:1px solid var(--border);
         vertical-align:top; word-break:break-word; }
th { background:#172033; color:var(--muted); font-weight:600; font-size:13px;
     text-transform:uppercase; letter-spacing:.03em; }
tr:last-child td { border-bottom:none; }

/* Tarjeta de registro (lectura humana) */
.record { background:var(--card); border:1px solid var(--border); border-radius:10px;
          padding:18px 22px; margin-bottom:16px; }
.record-head { display:flex; align-items:baseline; gap:12px; margin-bottom:12px; flex-wrap:wrap; }
.record-head .idx { color:var(--muted); font-size:13px; font-variant-numeric:tabular-nums; }
.record-head .name { font-size:16px; font-weight:600; word-break:break-word; }
.kv { display:grid; grid-template-columns:max-content 1fr; gap:6px 18px; margin:0; }
.kv dt { color:var(--muted); font-size:13px; white-space:nowrap; }
.kv dd { margin:0; word-break:break-word; }
.kv .sub { margin-top:4px; }

/* Etiquetas de estado */
.pill { display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px;
        font-weight:600; border:1px solid; }
.pill.ok { color:var(--ok); border-color:var(--ok); background:rgba(74,222,128,.08); }
.pill.warn { color:var(--warn); border-color:var(--warn); background:rgba(251,191,36,.08); }
.pill.err { color:var(--err); border-color:var(--err); background:rgba(248,113,113,.08); }

/* Graficos de barras */
.bar-row { display:grid; grid-template-columns:220px 1fr 48px; gap:12px; align-items:center;
           margin:6px 0; }
.bar-label { color:var(--fg); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.bar-track { background:#0b1220; border-radius:6px; height:18px; overflow:hidden; }
.bar-fill { height:100%; background:linear-gradient(90deg,#0ea5e9,#38bdf8); border-radius:6px; }
.bar-value { color:var(--muted); text-align:right; font-variant-numeric:tabular-nums; }
"""

# Etiquetas legibles para las claves internas de los registros.
LABELS: dict[str, str] = {
    "type": "Tipo de dato",
    "value": "Valor buscado",
    "source": "Fuente",
    "title": "Titulo",
    "url": "URL",
    "snippet": "Extracto",
    "query": "Consulta",
    "captured_at": "Capturado",
    "source_url": "URL de origen",
    "status": "Estado HTTP",
    "http": "HTTP",
    "error": "Error",
    "depth": "Profundidad",
    "links_found": "Enlaces encontrados",
    "domain": "Dominio",
    "ips": "Direcciones IP",
    "mx": "Registros MX",
    "ns": "Servidores de nombres",
    "txt": "Registros TXT",
    "technologies": "Tecnologias",
    "robots": "robots.txt",
    "tls": "Certificado TLS",
    "final_url": "URL final",
    "server": "Servidor",
    "headers": "Cabeceras",
    "issuer": "Emisor",
    "subject": "Titular",
    "not_before": "Valido desde",
    "not_after": "Valido hasta",
    "san": "Nombres alternativos (SAN)",
    "exists": "Existe",
    "sitemaps": "Sitemaps",
    "crawl_delay": "Retardo de rastreo",
    "can_fetch_root": "Permite acceder a la raiz",
}

# Claves que se muestran primero y con formato especial.
_PRIORITY = ("title", "name", "url", "source", "type", "value")


def _label(key: str) -> str:
    return LABELS.get(key, key.replace("_", " ").capitalize())


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _counter(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    """Cuenta valores escalares de un campo, buscando tambien en dicts anidados
    y aplanando listas (p. ej. 'technologies')."""
    counts: dict[str, int] = {}

    def visit(value: Any) -> None:
        if _is_scalar(value):
            if value is not None:
                label = str(value)
                counts[label] = counts.get(label, 0) + 1
        elif isinstance(value, list):
            for item in value:
                if _is_scalar(item) and item is not None:
                    label = str(item)
                    counts[label] = counts.get(label, 0) + 1
        elif isinstance(value, dict):
            for nested in value.values():
                visit(nested)

    for record in records:
        if key in record:
            visit(record[key])
    return counts


def _bar_chart(counts: dict[str, int], *, top: int = 10) -> str:
    if not counts:
        return ""
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    peak = max(v for _, v in items) or 1
    rows = ""
    for label, value in items:
        width = max(2, round(value / peak * 100))
        rows += (
            f'<div class="bar-row"><div class="bar-label" title="{html.escape(label)}">'
            f"{html.escape(label)}</div>"
            f'<div class="bar-track"><div class="bar-fill" style="width:{width}%"></div></div>'
            f'<div class="bar-value">{value}</div></div>'
        )
    return f'<div class="bars">{rows}</div>'


def _status_pill(record: dict[str, Any]) -> str:
    if record.get("error"):
        return f'<span class="pill err">{html.escape(str(record["error"]))[:60]}</span>'
    status = record.get("status")
    if status is None:
        http = record.get("http")
        status = http.get("status") if isinstance(http, dict) else None
    if not isinstance(status, int):
        return ""
    cls = "ok" if 200 <= status < 300 else "warn" if 300 <= status < 400 else "err"
    return f'<span class="pill {cls}">HTTP {status}</span>'


def _format_value(value: Any) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return '<span class="empty">-</span>'
    if isinstance(value, bool):
        return "Si" if value else "No"
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            return f'<a href="{html.escape(value)}" target="_blank" rel="noopener">{html.escape(value)}</a>'
        return html.escape(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if all(_is_scalar(v) for v in value):
            return "".join(_format_value(v) + "<br>" for v in value).rstrip("<br>")
        return f"<code>{html.escape(json.dumps(value, ensure_ascii=False))}</code>"
    if isinstance(value, dict):
        inner = "".join(
            f'<dt>{html.escape(_label(k))}</dt><dd>{_format_value(v)}</dd>' for k, v in value.items()
        )
        return f'<div class="sub"><dl class="kv">{inner}</dl></div>'
    return f"<code>{html.escape(json.dumps(value, ensure_ascii=False))}</code>"


def _record_title(record: dict[str, Any], index: int) -> str:
    for key in ("title", "name", "url", "domain", "source_url", "value"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"Registro {index}"


def _record_card(record: dict[str, Any], index: int) -> str:
    """Convierte un registro en una tarjeta clara con pares etiqueta/valor."""
    title = _record_title(record, index + 1)
    title_html = html.escape(title)
    if title.startswith(("http://", "https://")):
        title_html = f'<a href="{html.escape(title)}" target="_blank" rel="noopener">{title_html}</a>'
    pill = _status_pill(record)

    ordered = [k for k in _PRIORITY if k in record]
    ordered += [k for k in record if k not in ordered and k != "captured_at"]
    pairs = "".join(
        f"<dt>{html.escape(_label(k))}</dt><dd>{_format_value(record[k])}</dd>" for k in ordered
    )
    captured = record.get("captured_at")
    captured_html = (
        f'<dt>{html.escape(_label("captured_at"))}</dt><dd>{html.escape(str(captured))}</dd>'
        if captured
        else ""
    )
    return (
        f'<div class="record"><div class="record-head">'
        f'<span class="idx">#{index + 1}</span>'
        f'<span class="name">{title_html}</span>{pill}'
        f"</div>"
        f'<dl class="kv">{pairs}{captured_html}</dl></div>'
    )


def _summary_html(records: list[dict[str, Any]]) -> str:
    domains = {r.get("domain") for r in records if r.get("domain")}
    urls = {r.get("url") or r.get("source_url") for r in records if r.get("url") or r.get("source_url")}
    errors = sum(1 for r in records if r.get("error"))
    cards = [
        ("Registros", len(records)),
        ("Dominios", len(domains)),
        ("URLs", len(urls)),
        ("Con error", errors),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="num">{value}</div><div class="label">{html.escape(label)}</div></div>'
        for label, value in cards
    )

    blocks = ""
    sources = _counter(records, "source")
    if sources:
        blocks += f"<h3>Fuentes</h3>{_bar_chart(sources)}"
    statuses = _counter(records, "status") or _counter(records, "http")
    if statuses:
        blocks += f"<h3>Estados HTTP</h3>{_bar_chart(statuses)}"
    techs = _counter(records, "technologies")
    if techs:
        blocks += f"<h3>Tecnologias</h3>{_bar_chart(techs)}"
    by_domain = _counter(records, "domain")
    if by_domain:
        blocks += f"<h3>Registros por dominio</h3>{_bar_chart(by_domain)}"

    return f'<div class="cards">{cards_html}</div>{blocks}'


def _index_table(records: list[dict[str, Any]]) -> str:
    """Tabla-resumen compacta con una fila por registro."""
    if not records:
        return '<p class="empty">Sin registros.</p>'
    body = ""
    for i, record in enumerate(records):
        title = _record_title(record, i + 1)
        if title.startswith(("http://", "https://")):
            title_cell = f'<a href="{html.escape(title)}" target="_blank" rel="noopener">{html.escape(title)}</a>'
        else:
            title_cell = html.escape(title)
        source = record.get("source") or record.get("domain") or "-"
        body += (
            f'<tr><td>{i + 1}</td><td>{html.escape(str(source))}</td>'
            f"<td>{title_cell}</td><td>{_status_pill(record) or '-'}</td></tr>"
        )
    return (
        "<table><thead><tr><th>#</th><th>Fuente</th><th>Hallazgo</th><th>Estado</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def build_report(
    records: Iterable[dict[str, Any]],
    *,
    title: str = "Informe OSINT",
    subtitle: str | None = None,
) -> str:
    """Devuelve el HTML completo del informe, pensado para lectura humana."""
    rows = list(records)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if rows:
        cards = "".join(_record_card(record, i) for i, record in enumerate(rows))
        findings = f'<div class="records">{cards}</div>'
    else:
        findings = '<p class="empty">No se encontraron hallazgos para esta consulta.</p>'

    raw = html.escape(json.dumps(rows, ensure_ascii=False, indent=2))
    subtitle_html = f'<div class="meta">{html.escape(subtitle)}</div>' if subtitle else ""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>{html.escape(title)}</h1>
  <div class="meta">Generado: {generated} &middot; <span class="badge">{len(rows)} hallazgo(s)</span></div>
  {subtitle_html}
</header>
<main>
  <section>
    <h2>Resumen</h2>
    {_summary_html(rows)}
  </section>
  <section>
    <h2>Indice de hallazgos</h2>
    {_index_table(rows)}
  </section>
  <section>
    <h2>Detalle de hallazgos</h2>
    {findings}
  </section>
  <section>
    <h2>Datos completos (JSON)</h2>
    <details><summary>Mostrar datos sin procesar</summary><pre>{raw}</pre></details>
  </section>
</main>
<footer>
  <p><strong>osintkit</strong> &middot; informe generado a partir de fuentes publicas. Verifica la informacion antes de usarla.</p>
  <p><strong>Aviso legal:</strong> los datos pueden incluir informacion personal (nombres, telefonos, correos, identificaciones).
  Su tratamiento debe tener una base legal (consentimiento, interes legitimo o fin periodistico/investigativo) conforme al
  RGPD y a la normativa local de proteccion de datos (p. ej. Ley 8968 en Costa Rica). Aplica minimizacion y limita la
  retencion: elimina este archivo cuando deje de ser necesario. El uso indebido es responsabilidad exclusiva de quien lo realiza.</p>
</footer>
</body>
</html>
"""


def write_report(
    records: Iterable[dict[str, Any]],
    path: str,
    *,
    title: str = "Informe OSINT",
    subtitle: str | None = None,
) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(build_report(records, title=title, subtitle=subtitle))
    return path
