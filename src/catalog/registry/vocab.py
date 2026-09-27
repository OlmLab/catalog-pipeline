"""Controlled vocabularies of the registry tier (config/scope.yaml + config/vocab/*.yaml) and term matchers.

Matching semantics (documented in config/vocab/body_sites.yaml):
* term ending in '*'  → stem: ``\\b<stem>\\w*``
* plain term          → whole word, optional trailing 's' (``\\bgut(?:s)?\\b``) — "gut" never matches "Gutierrez",
                        "rat" never matches "ulcerative", "kid" never matches "kidney", "cat" never matches "applications"
* multi-word term     → words joined by ``[\\s\\-–]+``
* negative_terms      → any match whose span lies inside a negative-term span is dropped
Everything is case-insensitive except upper-case acronyms of ≤ 4 letters (BAL, CSF, NEC, ICU, NICU, IBD, HIV, ASD, COPD),
which are matched case-sensitively so that "bal" or "nec" inside ordinary text do not fire.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
CONFIG_DIR = os.environ.get("CATALOG_CONFIG_DIR", os.path.join(REPO_ROOT, "config"))

VOCAB_NAMES = ("body_sites", "life_stages", "assay", "population_flags")
SCHEMA_VERSION = 1


class VocabError(ValueError):
    pass


# --------------------------------------------------------------------------- loading
@lru_cache(maxsize=None)
def load_scope(path: str | None = None) -> dict[str, Any]:
    path = path or os.path.join(CONFIG_DIR, "scope.yaml")
    cfg = yaml.safe_load(open(path, encoding="utf-8"))
    if cfg.get("schema_version") != SCHEMA_VERSION:
        raise VocabError(f"scope.yaml schema_version {cfg.get('schema_version')} != {SCHEMA_VERSION}")
    ids = [s["id"] for s in cfg["scopes"]]
    if len(ids) != len(set(ids)):
        raise VocabError("duplicate scope ids in scope.yaml")
    return cfg


@lru_cache(maxsize=None)
def load_vocab(name: str, path: str | None = None) -> dict[str, Any]:
    if name not in VOCAB_NAMES:
        raise VocabError(f"unknown vocabulary {name!r}; known: {VOCAB_NAMES}")
    if path is None:
        scope = load_scope()
        rel = scope["vocabularies"][name]
        path = rel if os.path.isabs(rel) else os.path.join(os.path.dirname(CONFIG_DIR), rel)
        if not os.path.exists(path):  # CONFIG_DIR override that is not <repo>/config
            path = os.path.join(CONFIG_DIR, "vocab", f"{name}.yaml")
    v = yaml.safe_load(open(path, encoding="utf-8"))
    if v.get("schema_version") != SCHEMA_VERSION or v.get("vocabulary") != name:
        raise VocabError(f"{path}: bad schema_version/vocabulary header")
    if not v.get("codes"):
        raise VocabError(f"{path}: no codes")
    return v


def codes(name: str) -> list[str]:
    return list(load_vocab(name)["codes"].keys())


def scope_ids() -> list[str]:
    return [s["id"] for s in load_scope()["scopes"]]


def uberon_lookup(body_site_code: str) -> list[dict[str, str]]:
    """UBERON ids for a body-site code → [{id, label}, ...] (empty for other/unknown/multi)."""
    v = load_vocab("body_sites")
    if body_site_code not in v["codes"]:
        raise VocabError(f"unknown body_site code {body_site_code!r}")
    return list(v["codes"][body_site_code].get("uberon") or [])


def uberon_primary_id(body_site_code: str) -> str | None:
    u = uberon_lookup(body_site_code)
    return u[0]["id"] if u else None


# --------------------------------------------------------------------------- matchers
_ACRONYM_RE = re.compile(r"^[A-Z][A-Z0-9]{1,3}$")


def term_regex(term: str) -> re.Pattern:
    """Compile one vocabulary term to a regex (see module docstring)."""
    t = term.strip()
    stem = t.endswith("*")
    if stem:
        t = t[:-1]
    words = re.split(r"[\s\-–]+", t)
    parts = [re.escape(w) for w in words]
    body = r"[\s\-–]+".join(parts)
    if stem:
        pat = rf"\b{body}\w*"
    else:
        pat = rf"\b{body}(?:s)?\b"
    flags = 0 if (len(words) == 1 and _ACRONYM_RE.match(words[0])) else re.IGNORECASE
    return re.compile(pat, flags)


class TermMatcher:
    """Matches the codes of one vocabulary in free text, honouring negative terms.

    ``match(text)`` → {code: [matched_span_str, ...]} (only codes with ≥ 1 surviving hit).
    ``first_hit(text, code)`` → the first surviving span or ''.
    """

    def __init__(self, vocab: dict[str, Any]):
        self.name = vocab["vocabulary"]
        self.pos: dict[str, list[re.Pattern]] = {}
        self.neg: dict[str, list[re.Pattern]] = {}
        for code, spec in vocab["codes"].items():
            self.pos[code] = [term_regex(t) for t in (spec.get("match_terms") or [])]
            self.neg[code] = [term_regex(t) for t in (spec.get("negative_terms") or [])]

    def _neg_spans(self, code: str, text: str) -> list[tuple[int, int]]:
        spans = []
        for rx in self.neg[code]:
            spans.extend(m.span() for m in rx.finditer(text))
        return spans

    def match_spans(self, text: str | None, codes_subset: list[str] | None = None) -> dict[str, list[tuple[str, int, int]]]:
        """{code: [(matched_text, start, end), ...]} — surviving hits only, in text order."""
        if not text:
            return {}
        text = str(text)
        out: dict[str, list[tuple[str, int, int]]] = {}
        for code, rxs in self.pos.items():
            if codes_subset is not None and code not in codes_subset:
                continue
            if not rxs:
                continue
            neg = self._neg_spans(code, text)
            hits = []
            for rx in rxs:
                for m in rx.finditer(text):
                    s, e = m.span()
                    if any(ns <= s and e <= ne for ns, ne in neg):
                        continue
                    hits.append((m.group(0), s, e))
            if hits:
                out[code] = sorted(hits, key=lambda h: h[1])
        return out

    def match(self, text: str | None, codes_subset: list[str] | None = None) -> dict[str, list[str]]:
        return {c: [h[0] for h in hs] for c, hs in self.match_spans(text, codes_subset).items()}

    def first_hit(self, text: str | None, code: str) -> str:
        h = self.match(text, [code]).get(code) or []
        return h[0] if h else ""


@lru_cache(maxsize=None)
def matcher(name: str) -> TermMatcher:
    return TermMatcher(load_vocab(name))


def taxon_body_site_prior(scientific_name: str | None) -> str | None:
    """Weak taxon → body-site prior (TAXON IS NOT BODY SITE; confidence 0.5)."""
    if not scientific_name:
        return None
    pri = load_vocab("body_sites").get("taxon_priors") or {}
    return pri.get(str(scientific_name).strip().lower())


def age_days_to_life_stage(days: float | None) -> str | None:
    if days is None:
        return None
    bins = load_vocab("life_stages")["age_days_bins"]
    for code, (lo, hi) in bins.items():
        if lo <= days <= hi:
            return code
    return None


def validate_codes(name: str, values: list[str]) -> tuple[bool, str]:
    known = set(codes(name))
    bad = [v for v in values if v not in known]
    return (not bad), (f"{name}: unknown codes {bad}" if bad else "")
