"""Reconocimiento pasivo de un dominio usando solo fuentes públicas.

No realiza escaneo de puertos ni pruebas de intrusión: únicamente consulta
DNS, certificado TLS, cabeceras HTTP y robots.txt, que son información
pública que cualquier cliente web obtiene al visitar el sitio.
"""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import dns.resolver
import httpx

from ..http import Fetcher

TECH_SIGNATURES: dict[str, str] = {
    "wordpress": "WordPress",
    "wp-content": "WordPress",
    "drupal": "Drupal",
    "joomla": "Joomla",
    "shopify": "Shopify",
    "wix.com": "Wix",
    "squarespace": "Squarespace",
    "cloudflare": "Cloudflare",
    "nginx": "Nginx",
    "apache": "Apache",
    "microsoft-iis": "IIS",
    "react": "React",
    "vue": "Vue.js",
    "next.js": "Next.js",
    "jquery": "jQuery",
    "bootstrap": "Bootstrap",
    "google-analytics": "Google Analytics",
    "gtag/js": "Google Tag Manager",
}


@dataclass
class DomainReport:
    domain: str
    ips: list[str] = field(default_factory=list)
    mx: list[str] = field(default_factory=list)
    ns: list[str] = field(default_factory=list)
    txt: list[str] = field(default_factory=list)
    http: dict = field(default_factory=dict)
    tls: dict = field(default_factory=dict)
    technologies: list[str] = field(default_factory=list)
    robots: dict = field(default_factory=dict)


def resolve(domain: str, record_type: str) -> list[str]:
    try:
        answers = dns.resolver.resolve(domain, record_type, lifetime=8)
        return sorted({r.to_text().strip('"') for r in answers})
    except Exception:
        return []


def resolve_ips(domain: str) -> list[str]:
    ips: set[str] = set()
    for rtype in ("A", "AAAA"):
        ips.update(resolve(domain, rtype))
    if not ips:
        try:
            ips.add(socket.gethostbyname(domain))
        except OSError:
            pass
    return sorted(ips)


def tls_info(domain: str, port: int = 443) -> dict:
    context = ssl.create_default_context()
    try:
        with socket.create_connection((domain, port), timeout=8) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as tls_sock:
                cert = tls_sock.getpeercert()
                not_after = cert.get("notAfter")
                expiry = None
                if not_after:
                    expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(
                        tzinfo=timezone.utc
                    ).isoformat()
                return {
                    "issuer": dict(x[0] for x in cert.get("issuer", [])),
                    "subject": dict(x[0] for x in cert.get("subject", [])),
                    "not_before": cert.get("notBefore"),
                    "not_after": expiry,
                    "san": [entry[1] for entry in cert.get("subjectAltName", [])],
                }
    except Exception as exc:
        return {"error": str(exc)}


def detect_technologies(headers: dict[str, str], html: str) -> list[str]:
    haystack = " ".join(f"{k}:{v}" for k, v in headers.items()).lower() + " " + html.lower()
    found = [name for token, name in TECH_SIGNATURES.items() if token in haystack]
    return sorted(set(found))


def robots_info(fetcher: Fetcher, base_url: str, user_agent: str = "*") -> dict:
    robots_url = urljoin(base_url, "/robots.txt")
    response = fetcher.get(robots_url)
    if not response.ok:
        return {"url": robots_url, "exists": False}
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return {
        "url": robots_url,
        "exists": True,
        "sitemaps": [line.split(":", 1)[1].strip() for line in response.text.splitlines() if line.lower().startswith("sitemap")],
        "crawl_delay": parser.crawl_delay(user_agent),
        "can_fetch_root": parser.can_fetch(user_agent, urljoin(base_url, "/")),
    }


def analyze_domain(fetcher: Fetcher, domain: str) -> DomainReport:
    domain = domain.strip().lower().removeprefix("http://").removeprefix("https://").strip("/")
    base_url = f"https://{domain}"
    report = DomainReport(domain=domain)
    report.ips = resolve_ips(domain)
    report.mx = resolve(domain, "MX")
    report.ns = resolve(domain, "NS")
    report.txt = resolve(domain, "TXT")
    report.tls = tls_info(domain)

    response = fetcher.get(base_url)
    if response.ok:
        report.http = {
            "status": response.status,
            "final_url": response.url,
            "server": response.headers.get("server"),
            "headers": {
                k: v
                for k, v in response.headers.items()
                if k.lower()
                in {"server", "x-powered-by", "content-type", "strict-transport-security", "content-security-policy", "x-frame-options"}
            },
        }
        report.technologies = detect_technologies(response.headers, response.text)
    else:
        report.http = {"status": response.status, "error": response.headers.get("error")}

    report.robots = robots_info(fetcher, base_url)
    return report
