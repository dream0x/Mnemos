"""Generate Mnemos avatar candidates via FLUX [dev].

Run:  python scripts/make_avatar.py
Outputs: docs/avatar-{1,2,3}.png  (1024x1024 square)
"""
from __future__ import annotations
import os
import sys
import time
from pathlib import Path

import fal_client
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import cfg  # noqa: E402

OUT = ROOT / "docs"
OUT.mkdir(parents=True, exist_ok=True)

# Same aesthetic anchor as tarot/render.py so the avatar feels like part of the deck.
DECK_STYLE = (
    "ornate hand-painted art-nouveau illustration, "
    "muted indigo and antique gold palette with deep crimson accents, "
    "soft volumetric lighting, painterly textures, "
    "thin gilt circular border with small symbolic glyphs evenly spaced around the rim, "
    "centered single subject, mystical and quietly dramatic mood, "
    "no text, no letters, no inscription, no caption strip, "
    "vertical symmetry, symbol-like composition that reads at small size"
)

CANDIDATES = [
    # 1. Mnemosyne / titan goddess holding a mirror — most literal to the brand
    ("avatar-1.png",
     "a serene Greek titan goddess Mnemosyne facing forward, "
     "holding a small ornate hand-mirror reflecting a single bright star, "
     "long dark hair flowing, crown of golden olive leaves, "
     "deep indigo robes with gold embroidery, gentle closed-mouth smile"),

    # 2. Stylized art-deco mirror with cards orbiting
    ("avatar-2.png",
     "a tall oval gilt-framed mirror at center, art-nouveau filigree, "
     "the mirror surface glowing with a soft inner moon-light, "
     "three small ornate tarot cards floating in orbit around it, "
     "symmetric arrangement, dark indigo background with subtle constellations"),

    # 3. Luna moth + tarot symbol motif (more abstract / iconic)
    ("avatar-3.png",
     "a large luna moth with wings spread fully open facing forward, "
     "wings patterned with tarot suit symbols (cup, sword, wand, pentacle) "
     "rendered in gold leaf, body and antennae glowing softly, "
     "deep indigo void background with a single golden eight-pointed star above"),
]


def render(name: str, subject: str) -> Path:
    if not cfg.fal_key:
        raise SystemExit("FAL_KEY not set")
    os.environ["FAL_KEY"] = cfg.fal_key
    prompt = f"{DECK_STYLE}, depicting {subject}"
    print(f"\n→ {name}")
    print(f"  prompt: {prompt[:140]}…")
    t = time.time()
    result = fal_client.subscribe(
        "fal-ai/flux/dev",
        arguments={
            "prompt": prompt,
            "image_size": "square_hd",        # 1024x1024
            "num_inference_steps": 32,
            "num_images": 1,
            "guidance_scale": 5.0,
            "enable_safety_checker": False,
            "seed": abs(hash(name)) % (2**31),
        },
        with_logs=False,
    )
    url = result["images"][0]["url"]
    out = OUT / name
    out.write_bytes(requests.get(url, timeout=60).content)
    print(f"  → {out} ({out.stat().st_size//1024} KB, {time.time()-t:.1f}s)")
    return out


if __name__ == "__main__":
    for name, subject in CANDIDATES:
        render(name, subject)
    print("\nAll three avatars saved to docs/avatar-*.png")
    print("Pick one, then upload to @BotFather → /setuserpic for @mnemos_oracle_bot.")
