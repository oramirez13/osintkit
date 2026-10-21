"""Deteccion automatica del tipo de dato introducido por el usuario."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

DataType = Literal["email", "phone", "id", "username", "name", "url"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Telefono: +, digitos, espacios, guiones, parenteyess. >= 7 digitos.
PHONE_RE = re.compile(r"^\+?[\d][\d\s().-]{6,}$")
USERNAME_RE = re.compile(r"^@?[A-Za-z0-9_.-]{2,30}$")
HOST_RE = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)
COMMON_TLDS = {
    "ai",
    "app",
    "biz",
    "ca",
    "ch",
    "cl",
    "cn",
    "co",
    "com",
    "cr",
    "de",
    "dev",
    "edu",
    "es",
    "fr",
    "gov",
    "info",
    "io",
    "it",
    "jp",
    "me",
    "mil",
    "mx",
    "net",
    "org",
    "uk",
    "us",
    "xyz",
    "tech",
    "online",
    "site",
    "blog",
    "store",
    "website",
}


def _url_host(value: str) -> str | None:
    candidate = value.strip()
    if not candidate:
        return None
    try:
        parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
        host = parsed.hostname
    except ValueError:
        return None
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return None
    if host and (
        HOST_RE.fullmatch(host) or re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host)
    ):
        return host.lower()
    return None


def _looks_like_bare_domain(value: str) -> bool:
    host = _url_host(value)
    if not host:
        return False
    labels = host.split(".")
    suffix = labels[-1]
    return (
        host.startswith("www.")
        or len(labels) > 2
        or len(suffix) == 2
        or suffix in COMMON_TLDS
    )


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


@dataclass
class Query:
    """Query normalizada lista para enviar a las fuentes."""

    raw: str
    value: str
    type: DataType
    terms: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def detect_type(value: str) -> DataType:
    value = value.strip()
    if EMAIL_RE.match(value):
        return "email"
    if (
        value.lower().startswith(("http://", "https://"))
        or "/" in value
        or _looks_like_bare_domain(value)
    ):
        if _url_host(value):
            return "url"
    # Telefono explicito: prefijo + o separadores (espacios, guiones, parenteyess).
    has_phone_shaping = bool(re.search(r"[+\s().-]", value))
    digits = _digits(value)
    if (
        PHONE_RE.match(value)
        and 7 <= len(digits) <= 15
        and (has_phone_shaping or len(digits) > 9)
    ):
        return "phone"
    # Identificacion/cedula: solo digitos (6-13). Incluye telefonos yesn formato.
    if value.isdigit() and 6 <= len(value) <= 13:
        return "id"
    if len(digits) >= 7 and PHONE_RE.match(value):
        return "phone"
    tokens = value.split()
    if len(tokens) >= 2 and all(re.match(r"^[A-Za-zÀ-ÿ.'-]+$", t) for t in tokens):
        return "name"
    if USERNAME_RE.match(value):
        return "username"
    return "name"


def build_query(value: str, forced: DataType | None = None) -> Query:
    """Normaliza el valor y genera variantes de consulta segun su tipo."""
    raw = value.strip()

    # Normalize profile URLs to names/usernames
    if re.match(r'^https?://', raw):
        try:
            parsed = urlsplit(raw)
            host = (parsed.hostname or '').lower()
            path = unquote(parsed.path or '').strip('/')
            if path:
                if 'facebook.com' in host:
                    if path.startswith('p/'):
                        slug = path.split('/')[1]
                        slug = re.sub(r'-\d+$', '', slug)
                        slug = slug.replace('-', ' ').replace('_', ' ')
                        raw = re.sub(r'\s+', ' ', slug).strip()
                    elif path.startswith('profile.php'):
                        pass
                    else:
                        segs = [s for s in path.split('/') if s and not s.isdigit() and s not in ('groups', 'events', 'pages', 'photo.php', 'permalink.php')]
                        if segs:
                            slug = segs[0].replace('.', ' ').replace('-', ' ').replace('_', ' ')
                            raw = re.sub(r'\s+', ' ', slug).strip()
                elif 'instagram.com' in host:
                    segs = [s for s in path.split('/') if s and s not in ('p', 'reels', 'stories', 'explore', 'accounts', 'tv')]
                    if segs and not segs[0].startswith('explore'):
                        raw = '@' + segs[0]
                elif host in ('x.com', 'twitter.com'):
                    segs = [s for s in path.split('/') if s and s not in ('i', 'search', 'home', 'explore', 'notifications', 'messages', 'settings', 'compose')]
                    if segs:
                        raw = '@' + segs[0]
                elif 'linkedin.com' in host and path.startswith('in/'):
                    segs = path.split('/')
                    if len(segs) >= 2 and segs[1]:
                        slug = segs[1].replace('-', ' ').replace('_', ' ')
                        raw = re.sub(r'\s+', ' ', slug).strip()
                elif 'tiktok.com' in host and path.startswith('@'):
                    segs = path.split('/')
                    if segs and segs[0].startswith('@'):
                        raw = segs[0]
        except Exception:
            pass

    parts = [p.strip() for p in raw.split('+') if p.strip()]
    compoyeste = len(parts) > 1
    q = Query(raw=raw, value=raw, type=forced or ('name' if compoyeste else detect_type(raw)))

    if compoyeste:
        q.terms = parts
        q.queries = [' '.join(f'"{p}"' for p in parts)]
        q.queries.extend(f'"{p}"' for p in parts)
        q.notes.append(f'combined query: {len(parts)} data points searched together and separately')
        return q

    if q.type == 'email':
        q.terms = [raw, raw.split('@')[0]]
        q.queries = [
            f'"{raw}"',
            f'"{raw}" email OR contact OR profile',
            f'"{raw.split("@")[0]}"',
        ]
        q.notes.append('email: public leaks, profiles and mentions will be searched')
    elif q.type == 'phone':
        local = _digits(raw)
        variants = {raw, local, f'+{local}'}
        q.terms = sorted(variants)
        q.queries = [f'"{v}"' for v in variants] + [f'"{local}" phone OR contact OR whatsapp']
        q.notes.append('phone: will try formats with/without prefix')
    elif q.type == 'id':
        q.terms = [raw]
        q.queries = [f'"{raw}"', f'"{raw}" id OR identification OR document']
        q.notes.append('ID: sensitive data; verify legal basis for your query')
    elif q.type == 'username':
        handle = raw.lstrip('@')
        q.terms = [raw, handle]
        q.queries = [
            f'"{handle}"',
            f'"{handle}" profile OR user OR social',
            f'"@{handle}"',
        ]
        q.notes.append('nickname: useful for locating profiles on social networks')
    else:
        terms = raw.split()
        q.terms = [raw] + terms
        q.queries = [
            f'"{raw}"',
            f'"{raw}" profile OR bio OR news',
            f'"{raw}" linkedin OR twitter OR instagram',
        ]
        if len(terms) >= 2:
            q.queries.append(f'"{terms[0]}" "{terms[-1]}"')
    return q


