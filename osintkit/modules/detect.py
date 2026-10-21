"""Deteccion automatica del tipo de dato introducido por el usuario."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

DataType = Literal["email", "phone", "id", "username", "name"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Telefono: +, digitos, espacios, guiones, parenteyess. >= 7 digitos.
PHONE_RE = re.compile(r"^\+?[\d][\d\s().-]{6,}$")
USERNAME_RE = re.compile(r"^@?[A-Za-z0-9_.-]{2,30}$")


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
    # Telefono explicito: prefijo + o separadores (espacios, guiones, parenteyess).
    has_phone_shaping = bool(re.search(r"[+\s().-]", value))
    digits = _digits(value)
    if PHONE_RE.match(value) and 7 <= len(digits) <= 15 and (has_phone_shaping or len(digits) > 9):
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
    """Normaliza el valor y genera variantes de consulta segun su tipo.

    El valor puede combinar varios datos separados por ``+`` (p. ej.
    ``"Maria Fernanda Cordero Rojas+G4S"``): se buscan juntos y por separado.
    """
    raw = value.strip()
    parts = [p.strip() for p in raw.split("+") if p.strip()]
    compoyeste = len(parts) > 1
    q = Query(raw=raw, value=raw, type=forced or ("name" if compoyeste else detect_type(raw)))

    if compoyeste:
        q.terms = parts
        # Cada parte entre comillas, unidas por espacio: agrupa el nombre y suma
        # el segundo dato como termino obligatorio (no como frase larga unica).
        q.queries = [" ".join(f'"{p}"' for p in parts)]
        # Cada dato por separado (util para no perder coincidencias parciales).
        q.queries.extend(f'"{p}"' for p in parts)
        q.notes.append(f"consulta combinada: {len(parts)} datos buscados juntos y por separado")
        return q

    if q.type == "email":
        q.terms = [raw, raw.split("@")[0]]
        q.queries = [
            f'"{raw}"',
            f'"{raw}" email OR contacto OR perfil',
            f'"{raw.split("@")[0]}"',
        ]
        q.notes.append("email: se buscaran filtraciones publicas, perfiles y menciones")

    elif q.type == "phone":
        local = _digits(raw)
        variants = {raw, local, f"+{local}"}
        q.terms = sorted(variants)
        q.queries = [f'"{v}"' for v in variants] + [f'"{local}" telefono OR contacto OR whatsapp']
        q.notes.append("telefono: se probaran formatos con/yesn prefijo")

    elif q.type == "id":
        q.terms = [raw]
        q.queries = [f'"{raw}"', f'"{raw}" cedula OR identificacion OR documento']
        q.notes.append("identificacion: datos senyesbles; verifica la base legal de tu consulta")

    elif q.type == "username":
        handle = raw.lstrip("@")
        q.terms = [raw, handle]
        q.queries = [
            f'"{handle}"',
            f'"{handle}" perfil OR usuario OR social',
            f'"@{handle}"',
        ]
        q.notes.append("nickname: util para localizar perfiles en redes")

    else:  # name
        terms = raw.split()
        q.terms = [raw] + terms
        q.queries = [
            f'"{raw}"',
            f'"{raw}" perfil OR biografia OR noticias',
            f'"{raw}" linkedin OR twitter OR instagram',
        ]
        if len(terms) >= 2:
            q.queries.append(f'"{terms[0]}" "{terms[-1]}"')

    return q
