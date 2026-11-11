"""Scoring between a family's report and a camp registration.

Face similarity carries most of the weight when both sides have a photo.
Text details (gender, age, name, origin, marks) are the fallback and also
act as a sanity check on face matches.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

import numpy as np

from face_engine import engine

MIN_SAVE = 45.0       # candidates below this are not stored
LIKELY = 70.0         # shown as "likely match"
TEXT_CAP = 82.0       # text-only matches never claim more than this


def _tokens(s: str | None) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2}


def _overlap(a: str | None, b: str | None) -> float | None:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return None
    hits = 0
    for x in ta:
        if any(x == y or (len(x) > 3 and SequenceMatcher(None, x, y).ratio() > 0.8) for y in tb):
            hits += 1
    return hits / len(ta)


def _name_sim(a: str | None, b: str | None) -> float | None:
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a or not b:
        return None
    full = SequenceMatcher(None, a, b).ratio()
    first = SequenceMatcher(None, a.split()[0], b.split()[0]).ratio()
    return max(full, first * 0.9)


def text_score(report, person) -> tuple[float | None, bool]:
    """Return (score 0-100 or None if nothing to compare, hard_mismatch)."""
    parts: list[tuple[float, float]] = []  # (weight, value 0-1)
    mismatch = False

    rg, pg = (report["gender"] or "").lower(), (person["gender"] or "").lower()
    if rg and pg and rg != "unknown" and pg != "unknown":
        same = rg == pg
        parts.append((2.0, 1.0 if same else 0.0))
        mismatch |= not same

    if report["age"] is not None and person["age"] is not None:
        diff = abs(int(report["age"]) - int(person["age"]))
        tol = max(3, 0.15 * int(report["age"]))
        val = max(0.0, 1.0 - diff / (2 * tol))
        parts.append((2.0, val))
        mismatch |= diff > 3 * tol

    ns = _name_sim(report["name"], person["name"])
    if ns is not None:
        parts.append((2.5, ns))

    loc = _overlap(report["last_seen"], f'{person["origin"] or ""}')
    if loc is not None:
        parts.append((1.5, loc))

    mk = _overlap(report["marks"], person["marks"])
    if mk is not None:
        parts.append((1.5, mk))

    if not parts:
        return None, mismatch
    total_w = sum(w for w, _ in parts)
    score = sum(w * v for w, v in parts) / total_w
    # Fewer fields compared = less certainty.
    # Age + gender alone describe thousands of people, so they score low;
    # name, place and marks are needed for a confident text-only match.
    coverage = min(1.0, total_w / 9.0)
    return round(score * 100 * (0.35 + 0.65 * coverage), 1), mismatch


def score(report, person) -> dict | None:
    face = None
    if report["embedding"] is not None and person["embedding"] is not None:
        a = np.frombuffer(report["embedding"], dtype=np.float32)
        b = np.frombuffer(person["embedding"], dtype=np.float32)
        if a.shape == b.shape:
            face = engine.confidence(engine.cosine(a, b))

    text, mismatch = text_score(report, person)

    if face is not None:
        conf = face if text is None else 0.85 * face + 0.15 * text
        method = "face" if text is None else "face+text"
        if mismatch:
            conf = min(conf, 60.0)
    elif text is not None:
        conf = min(text, TEXT_CAP)
        method = "text"
        if mismatch:
            conf = min(conf, 30.0)
    else:
        return None

    return {
        "confidence": round(conf, 1),
        "face_score": face,
        "text_score": text,
        "method": method,
    }
