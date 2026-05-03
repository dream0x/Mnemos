"""Per-user rate limits + global daily $ ceiling for Mnemos.

Tier rules (also encoded in config.Config.tier_of):
  - owner       : unlimited everything, can mint
  - allowlist   : ALLOWLIST_DAILY_READINGS / day, no mint
  - public      : PUBLIC_DAILY_READINGS / day, PUBLIC_LIFETIME_READINGS lifetime, no mint
  - public      : also blocked entirely if PUBLIC_ENABLED=false (kill switch)

Daily windows reset at UTC midnight. Global spend ceiling is enforced
across all non-owner traffic; owner is always served.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Literal

from config import cfg
from memory import _user_dir

Tier = Literal["owner", "allowlist", "public"]


# ----- Per-user quota state -----

@dataclass
class Quota:
    user_id: str
    day_key: str = ""           # "YYYY-MM-DD" (UTC)
    day_count: int = 0          # readings used today
    lifetime_count: int = 0     # readings used ever
    last_seen: float = 0.0


def _today_utc() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _quota_path(user_id: int | str) -> Path:
    return _user_dir(user_id) / "quota.json"


def load_quota(user_id: int | str) -> Quota:
    p = _quota_path(user_id)
    if not p.exists():
        return Quota(user_id=str(user_id))
    return Quota(**json.loads(p.read_text()))


def save_quota(q: Quota) -> None:
    _quota_path(q.user_id).write_text(json.dumps(asdict(q), indent=2))


# ----- Global $-spend tracker -----

GLOBAL_SPEND_PATH = Path(__file__).resolve().parent / "data" / "global_spend.json"


@dataclass
class GlobalSpend:
    day_key: str = ""
    spent_usd: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)  # by source: kimi, fal, pinata, gas


def _load_global() -> GlobalSpend:
    if not GLOBAL_SPEND_PATH.exists():
        return GlobalSpend()
    raw = json.loads(GLOBAL_SPEND_PATH.read_text())
    return GlobalSpend(**raw)


def _save_global(g: GlobalSpend) -> None:
    GLOBAL_SPEND_PATH.parent.mkdir(parents=True, exist_ok=True)
    GLOBAL_SPEND_PATH.write_text(json.dumps(asdict(g), indent=2))


def record_spend(amount_usd: float, source: str) -> GlobalSpend:
    today = _today_utc()
    g = _load_global()
    if g.day_key != today:
        g = GlobalSpend(day_key=today)
    g.spent_usd = round(g.spent_usd + amount_usd, 6)
    g.breakdown[source] = round(g.breakdown.get(source, 0.0) + amount_usd, 6)
    _save_global(g)
    return g


def todays_spend() -> GlobalSpend:
    g = _load_global()
    if g.day_key != _today_utc():
        return GlobalSpend(day_key=_today_utc())
    return g


# ----- The check -----

@dataclass
class Decision:
    allowed: bool
    tier: Tier
    reason: str = ""
    user_message: str = ""           # surface to the user verbatim if not allowed
    remaining_today: int | None = None


def check_can_read(user_id: int | str) -> Decision:
    """Call before serving any reading. If allowed=True, also call commit_read on success."""
    tier: Tier = cfg.tier_of(user_id)  # type: ignore[assignment]

    # 1. Kill switch
    if tier != "owner" and not cfg.public_enabled:
        return Decision(False, tier, "public_disabled",
                        "🌑 The oracle is resting right now. Try again later.")

    # 2. Global $ ceiling (owner bypasses)
    if tier != "owner":
        g = todays_spend()
        if g.spent_usd >= cfg.max_daily_usd_spend:
            return Decision(False, tier, "spend_ceiling",
                            "🕯️ Today's quota of cosmic energy is spent. The oracle returns at midnight UTC.")

    # 3. Per-tier rate limits
    q = load_quota(user_id)
    today = _today_utc()
    if q.day_key != today:
        q.day_key = today
        q.day_count = 0
        save_quota(q)

    if tier == "owner":
        return Decision(True, tier, "owner_unlimited", remaining_today=None)

    if tier == "allowlist":
        limit = cfg.allowlist_daily_readings
        if q.day_count >= limit:
            return Decision(False, tier, "allowlist_daily",
                            f"🌙 You've used today's {limit} readings. New cards arrive at midnight UTC.",
                            remaining_today=0)
        return Decision(True, tier, "ok", remaining_today=limit - q.day_count)

    # public
    if q.lifetime_count >= cfg.public_lifetime_readings:
        return Decision(False, tier, "public_lifetime",
                        "✨ You've sampled the deck — DM the dev for an invite to keep going.")
    daily = cfg.public_daily_readings
    if q.day_count >= daily:
        return Decision(False, tier, "public_daily",
                        f"🌙 That's all for today ({daily} readings). Come back tomorrow.",
                        remaining_today=0)
    return Decision(True, tier, "ok", remaining_today=daily - q.day_count)


def commit_read(user_id: int | str) -> Quota:
    """Increment counters AFTER a successful reading is served."""
    q = load_quota(user_id)
    today = _today_utc()
    if q.day_key != today:
        q.day_key = today
        q.day_count = 0
    q.day_count += 1
    q.lifetime_count += 1
    q.last_seen = time.time()
    save_quota(q)
    return q


def can_mint(user_id: int | str) -> Decision:
    """Mint is owner-only. (Trivial wrapper but kept here so callers are uniform.)"""
    if cfg.is_owner(user_id):
        return Decision(True, "owner", "owner_only")
    return Decision(False, "public", "owner_only_mint",
                    "🔒 Minting is currently owner-only. Public mint coming in v0.2.")


# ----- CLI for ops -----

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--check", type=int, help="user_id to check")
    p.add_argument("--show-spend", action="store_true")
    p.add_argument("--reset", type=int, help="user_id to wipe quota (DEV ONLY)")
    args = p.parse_args()

    if args.check is not None:
        d = check_can_read(args.check)
        print(asdict(d))
    if args.show_spend:
        print(asdict(todays_spend()))
    if args.reset is not None:
        path = _quota_path(args.reset)
        if path.exists():
            path.unlink()
            print(f"reset quota for {args.reset}")
        else:
            print("no quota file to reset")
