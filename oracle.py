"""Mnemos — public API.

Hermes Agent (or any caller) imports this module and calls the functions
below. Each tool returns a JSON-serializable dict so the agent can hand
results back to the user with no further glue.

Tone of all user-visible strings is set in `kimi.py`. This module only
shapes data and orchestrates calls.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict
from typing import Any

from tarot import deck as deck_mod
from memory import (
    Profile,
    Reading,
    append_reading,
    context_snapshot,
    find_reading,
    recent_readings,
    update_reading,
)

logger = logging.getLogger("mnemos")

SPREADS: dict[str, int] = {
    "single": 1,
    "three_card": 3,        # past / present / future
    "celtic_cross": 10,
}

SPREAD_POSITIONS: dict[str, list[str]] = {
    "single": ["the card"],
    "three_card": ["past", "present", "future"],
    "celtic_cross": [
        "the situation", "the challenge", "the past",
        "the recent past", "the crown / best outcome", "the near future",
        "yourself", "your environment", "hopes & fears", "outcome",
    ],
}


# ---------- Tool: pull_cards ----------

def pull_cards(
    user_id: int | str,
    question: str,
    spread: str = "three_card",
    *,
    allow_reversed: bool = True,
) -> dict[str, Any]:
    """Choose cards for a spread. Pure data; no image gen yet."""
    if spread not in SPREADS:
        raise ValueError(f"Unknown spread {spread!r}; choose from {list(SPREADS)}")
    n = SPREADS[spread]
    drawn = deck_mod.draw(n, allow_reversed=allow_reversed)
    positions = SPREAD_POSITIONS[spread]
    cards: list[dict[str, Any]] = []
    for (card, reversed_), pos in zip(drawn, positions, strict=True):
        cards.append({
            "id": card.id,
            "name": card.name,
            "arcana": card.arcana,
            "reversed": reversed_,
            "position": pos,
            "keywords": list(card.keywords),
            "meaning": card.reversed if reversed_ else card.upright,
            "art_prompt": card.art_prompt,
        })
    return {
        "user_id": str(user_id),
        "question": question,
        "spread": spread,
        "cards": cards,
        "drawn_at": time.time(),
    }


# ---------- Tool: render_cards ----------

def render_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Render each card via FLUX. Adds 'image_path' to each card dict."""
    from tarot.render import render_card  # lazy: needs fal.ai key
    out: list[dict[str, Any]] = []
    for c in cards:
        path = render_card(c["id"], c["art_prompt"], reversed_=c.get("reversed", False))
        out.append({**c, "image_path": str(path)})
    return out


# ---------- Tool: interpret_reading ----------

def interpret_reading(
    user_id: int | str,
    question: str,
    cards: list[dict[str, Any]],
    spread: str = "three_card",
) -> str:
    """Hand the spread to Kimi K2.6 with full memory context. Returns the prose."""
    from kimi import oracle_interpret  # lazy
    history_context = context_snapshot(user_id)
    return oracle_interpret(
        question=question,
        cards=cards,
        spread=spread,
        history_context=history_context,
    )


# ---------- Tool: full reading flow (convenience) ----------

def perform_reading(
    user_id: int | str,
    question: str,
    spread: str = "three_card",
    *,
    save: bool = True,
) -> dict[str, Any]:
    """Pull -> render -> interpret -> save. Returns full reading dict."""
    drawn = pull_cards(user_id, question, spread)
    rendered = render_cards(drawn["cards"])
    interpretation = interpret_reading(user_id, question, rendered, spread)

    reading = Reading(
        id=Reading.new_id(),
        user_id=str(user_id),
        timestamp=time.time(),
        question=question,
        spread=spread,
        cards=rendered,
        interpretation=interpretation,
    )
    if save:
        append_reading(reading)
    return asdict(reading)


# ---------- Tool: save_reading (manual override) ----------

def save_reading(reading_dict: dict[str, Any]) -> str:
    r = Reading(**reading_dict)
    append_reading(r)
    return r.id


# ---------- Tool: recall_history ----------

def recall_history(user_id: int | str, limit: int = 5) -> list[dict[str, Any]]:
    return [asdict(r) for r in recent_readings(user_id, limit=limit)]


# ---------- Tool: daily_horoscope ----------

def daily_horoscope(sign: str | None = None, user_id: int | str | None = None) -> str:
    """Daily horoscope for a sun sign (or the user's known sign)."""
    from kimi import oracle_daily  # lazy
    history_context = ""
    if user_id is not None:
        profile = Profile.load(user_id)
        sign = sign or profile.sun_sign
        history_context = context_snapshot(user_id, max_readings=5, max_chars=8_000)
    if not sign:
        raise ValueError("Need a sign or a user_id with a saved sun sign")
    return oracle_daily(sign=sign, history_context=history_context)


# ---------- Tool: set_profile ----------

def set_profile(user_id: int | str, **fields: Any) -> dict[str, Any]:
    p = Profile.load(user_id)
    for k, v in fields.items():
        if hasattr(p, k):
            setattr(p, k, v)
    p.save()
    return asdict(p)


# ---------- Tool: mint_card ----------

def mint_card(
    user_id: int | str,
    reading_id: str,
    card_index: int = 0,
    to_address: str | None = None,
) -> dict[str, Any]:
    """Mint the chosen card of a reading as ERC-721 on Base Sepolia. Owner-gated upstream."""
    from nft.mint import mint_oracle_card  # lazy

    reading = find_reading(user_id, reading_id)
    if not reading:
        raise ValueError(f"Reading {reading_id} not found for user {user_id}")
    if not reading.cards:
        raise ValueError("Reading has no cards")
    if card_index < 0 or card_index >= len(reading.cards):
        raise ValueError(f"card_index out of range")

    card = reading.cards[card_index]
    if not card.get("image_path"):
        raise ValueError("Card has no rendered image to mint")

    profile = Profile.load(user_id)
    recipient = to_address or profile.wallet_address
    if not recipient:
        raise ValueError("No wallet_address on profile and none provided")

    result = mint_oracle_card(
        recipient=recipient,
        card=card,
        question=reading.question,
        interpretation_excerpt=reading.interpretation[:500],
        reading_id=reading_id,
    )

    update_reading(
        user_id,
        reading_id,
        minted_token_id=result["token_id"],
        minted_tx=result["tx_hash"],
        minted_card_id=card["id"],
    )
    return result


# ---------- Module self-check ----------

if __name__ == "__main__":
    # No external API calls — just shape verification
    drawn = pull_cards("test", "What about my week?", "three_card")
    assert len(drawn["cards"]) == 3
    for c in drawn["cards"]:
        print(f"  [{c['position']:>10}] {c['name']}{' (R)' if c['reversed'] else ''}: {c['meaning']}")
    print("\noracle.py shape ok")
