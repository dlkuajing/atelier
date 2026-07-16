"""Canonical JSON bytes and domain-separated SHA-256 hashing for the O-01 kernel.

Deterministic serialization support consumed by the closed-world preregistration and
default-deny ITT modules; domain separation keeps every content hash distinct. Pure
UNRATIFIED support code — it grants no authority and cannot promote any north-star gate.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize the O-01 closed-world value without lossy normalization."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def domain_separated_hash(domain: str, value: Any) -> str:
    preimage = domain.encode("utf-8") + b"\x00" + canonical_json_bytes(value)
    return hashlib.sha256(preimage).hexdigest()


def exact_content_hash(domain: str, content: Mapping[str, Any]) -> str:
    if content.get("domain_tag") != domain:
        raise ValueError(f"content domain_tag must equal {domain!r}")
    return domain_separated_hash(
        domain,
        {key: value for key, value in content.items() if key != "domain_tag"},
    )
