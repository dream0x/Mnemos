"""Per-user persistence for Mnemos.

Layout:
    data/{telegram_user_id}/
        profile.json      # birth data, tone preferences, owner-set fields
        readings.jsonl    # append-only history (rich, fed back to Kimi K2.6)
        predictions.jsonl # for "did it come true?" tracking
        quota.json        # rate-limit state (managed by ratelimit.py)

All paths are scoped under DATA_ROOT (default: ./data). The Hermes
agent's own MEMORY.md / USER.md two-file system is *separate* and lives
under ~/.hermes/; we don't touch it directly.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Iterable

DATA_ROOT = Path(os.environ.get("ORACLE_DATA_ROOT", Path(__file__).parent / "data"))


def _user_dir(user_id: int | str) -> Path:
    p = DATA_ROOT / str(user_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------- Profile ----------

@dataclass
class Profile:
    user_id: str
    display_name: str | None = None
    dob: str | None = None              # ISO date "1995-04-12"
    birth_time: str | None = None       # "HH:MM" 24h, optional
    birth_place: str | None = None      # "Kyiv, Ukraine"
    sun_sign: str | None = None
    pronouns: str | None = None
    tone_preference: str | None = None  # e.g. "softer", "blunter"
    wallet_address: str | None = None   # for NFT mints
    notes: str = ""                     # free-form, owner-editable

    @classmethod
    def load(cls, user_id: int | str) -> "Profile":
        path = _user_dir(user_id) / "profile.json"
        if not path.exists():
            return cls(user_id=str(user_id))
        return cls(**json.loads(path.read_text()))

    def save(self) -> None:
        path = _user_dir(self.user_id) / "profile.json"
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False))


# ---------- Readings ----------

@dataclass
class Reading:
    id: str
    user_id: str
    timestamp: float
    question: str
    spread: str                          # "single", "three_card", "celtic_cross"
    cards: list[dict[str, Any]]          # [{"id": "the-fool", "name": "The Fool", "reversed": False, "image_path": "..."}]
    interpretation: str
    model: str = "kimi-k2.6"
    minted_token_id: int | None = None   # filled when NFT minted
    minted_tx: str | None = None
    minted_card_id: str | None = None    # which card was the hero (minted) one
    extra: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:12]


def append_reading(reading: Reading) -> None:
    path = _user_dir(reading.user_id) / "readings.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(reading), ensure_ascii=False) + "\n")


def all_readings(user_id: int | str) -> list[Reading]:
    path = _user_dir(user_id) / "readings.jsonl"
    if not path.exists():
        return []
    out: list[Reading] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        out.append(Reading(**d))
    return out


def recent_readings(user_id: int | str, limit: int = 5) -> list[Reading]:
    return all_readings(user_id)[-limit:]


def find_reading(user_id: int | str, reading_id: str) -> Reading | None:
    for r in all_readings(user_id):
        if r.id == reading_id:
            return r
    return None


def update_reading(user_id: int | str, reading_id: str, **fields: Any) -> Reading | None:
    """Rewrite the JSONL with one reading patched. Hot path is rare (mint flow)."""
    path = _user_dir(user_id) / "readings.jsonl"
    if not path.exists():
        return None
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    found: Reading | None = None
    for row in rows:
        if row["id"] == reading_id:
            row.update(fields)
            found = Reading(**row)
            break
    if found is None:
        return None
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    return found


# ---------- Predictions (optional, for "did it come true?") ----------

@dataclass
class Prediction:
    id: str
    user_id: str
    reading_id: str
    text: str                  # the predicted thing in plain words
    due: str                   # ISO date when we should check in
    resolved: bool = False
    outcome: str | None = None # "yes" | "partial" | "no" | None


def append_prediction(p: Prediction) -> None:
    path = _user_dir(p.user_id) / "predictions.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(p), ensure_ascii=False) + "\n")


def all_predictions(user_id: int | str) -> list[Prediction]:
    path = _user_dir(user_id) / "predictions.jsonl"
    if not path.exists():
        return []
    return [Prediction(**json.loads(l)) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------- Memory snapshot for Kimi context ----------

def context_snapshot(user_id: int | str, max_readings: int = 30, max_chars: int = 60_000) -> str:
    """Build a compact text blob to inject into Kimi's system prompt.

    Goal: leverage K2.6's 256K context without wasting tokens on duplicates.
    Truncates oldest readings first if budget is exceeded.
    """
    profile = Profile.load(user_id)
    readings = recent_readings(user_id, limit=max_readings)

    parts: list[str] = []
    parts.append("# User profile")
    parts.append(json.dumps(asdict(profile), ensure_ascii=False, indent=2))

    if readings:
        parts.append("\n# Past readings (most recent last)")
        for r in readings:
            ts = time.strftime("%Y-%m-%d", time.gmtime(r.timestamp))
            cards_str = ", ".join(
                f"{c['name']}{' reversed' if c.get('reversed') else ''}" for c in r.cards
            )
            parts.append(f"\n## {ts} — \"{r.question}\" ({r.spread})")
            parts.append(f"Cards: {cards_str}")
            parts.append(f"Reading:\n{r.interpretation}")

    blob = "\n".join(parts)
    if len(blob) > max_chars:
        # Keep profile + tail of readings
        keep_tail = max_chars - 2000
        blob = parts[0] + "\n" + parts[1] + "\n\n[... older readings truncated ...]\n" + blob[-keep_tail:]
    return blob
