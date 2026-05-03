# 🪞 Mnemos

> *the oracle that remembers every card it's ever pulled for you*

A divination companion built as a [Hermes Agent](https://hermes-agent.nousresearch.com/) skill. Mnemos pulls tarot spreads, paints the cards in a unified deck style with FLUX, and answers your question through them with **Kimi K2.6's 256K context** — using the entire history of readings it's ever given you. The hero card of each reading can be minted on **Base Sepolia** as an ERC-721 keepsake, viewable through a custom on-chain viewer.

> **Try it live:** [@hermeskimi_oracle_bot](https://t.me/hermeskimi_oracle_bot) on Telegram
> **View any minted card:** [the on-chain viewer](https://dream0x.github.io/Hermes-Tarot/?contract=0xa1b9bdeb72aa4f4b86c11234ea6301daa68d2c16&token=1)
>
> Public users get 3 readings/day (anti-abuse). Owner has unlimited use and minting.

Built for the [**Hermes Agent Creative Hackathon**](https://hermes-agent.nousresearch.com/) by [Nous Research](https://nousresearch.com/) × [Kimi (Moonshot AI)](https://www.kimi.com/), May 2026.

---

## Why this exists

The Hermes Agent ecosystem already has skills for FLUX images, Spotify playback, autonomous novel writing, and TouchDesigner. There was no skill for the **divination / personalization / spiritual companion** space — a category with massive Western mainstream traction (Co-Star: 30M users, WitchTok: billions of views).

Mnemos fills that gap and demonstrates Hermes' three real superpowers in one product:

| Hermes Agent strength | How Mnemos uses it |
|---|---|
| **Persistent memory** | Every reading is appended to a per-user JSONL; every new reading injects up to 30 prior readings into Kimi's 256K context — the oracle *literally remembers every card you've ever pulled* |
| **Scheduled tasks** (natural-language cron) | One tap on `📅 Daily at 9 AM UTC` registers a recurring job — your sun-sign horoscope arrives every morning, forever |
| **Multi-platform** | The same `oracle.py` skill runs through any Hermes transport — Telegram is the first; Discord/Slack/WhatsApp would need ~30 min of config, no code changes |

It also showcases **Kimi K2.6's 256K context** as a personalization engine, not just a long-doc reader.

---

## What makes a Mnemos reading different

Most chatbot tarot readers do one of two things: (a) describe each card in the abstract, or (b) generate a generic "you are entering a transformative phase" blob. Mnemos is engineered to do neither.

The system prompt forces a specific shape on every reading:

1. **Frame** — restate the question in one sentence that names *what kind* of question it is (timing? trust? readiness?). Show the user you heard them.
2. **Cards as answer** — one paragraph per card. Each paragraph translates the card's archetype into a concrete answer for *this* user's *specific* situation. No textbook recitation.
3. **Direction** — the final paragraph delivers a single, soft instruction. Not a prediction; a stance to hold. Ends with a body image (breath, posture, footing).
4. **Memory call-back** — when relevant, the reading references your prior readings ("Last week the Magician came to you — that cycle is closing now"). At most one per session.

All of this is delivered as plain prose, in English only, regardless of the language of the question.

---

## Architecture

```
┌─ Telegram ──────────────────────────┐
│  user message / /pull / /horoscope  │
└──────────────┬──────────────────────┘
               │
        ┌──────▼──────────┐
        │  bot.py         │  rate-limit gate + spend ceiling
        │  (transport)    │
        └──────┬──────────┘
               │  invokes
        ┌──────▼──────┐
        │  oracle.py  │  the Hermes skill (also discoverable to the agent itself)
        └──────┬──────┘
               │
   ┌───────────┼─────────────┬──────────────┐
   ▼           ▼             ▼              ▼
┌──────┐  ┌─────────┐   ┌──────────┐  ┌──────────┐
│ tarot│  │ astro   │   │  Kimi    │  │ memory   │
│ deck │  │ daily   │   │  K2.6    │  │ profile +│
│  +   │  │         │   │ (256K)   │  │ readings │
│ FLUX │  │         │   │          │  │ JSONL    │
└──┬───┘  └─────────┘   └──────────┘  └──────────┘
   │
   ▼ on "mint"
┌──────────────────┐
│ Pinata (IPFS)    │
│ → Base Sepolia   │
│   ERC-721        │
│ → custom viewer  │
└──────────────────┘
```

Critical files:

| Path | Role |
|---|---|
| `SKILL.md` | agentskills.io manifest Hermes auto-discovers |
| `oracle.py` | Public skill API — pull / render / interpret / mint / save |
| `bot.py` | Telegram transport (BotCommands menu, ConversationHandler onboarding, mint button) |
| `kimi.py` | Kimi K2.6 client with the locked persona + few-shot |
| `tarot/deck.py` | Full 78-card RWS dataset (public domain) |
| `tarot/render.py` | FLUX call + style-locked prompt + clean title overlay |
| `memory.py` | Per-user profile + reading history + Kimi context snapshot |
| `ratelimit.py` | Per-user quotas + global daily $ ceiling + kill switch |
| `nft/OracleCard.sol` | Minimal self-contained ERC-721 (no OZ imports) |
| `nft/mint.py` | Pinata pin + safeMint via web3.py |
| `docs/index.html` | Custom on-chain card viewer (GitHub Pages) |

---

## Setup

### Prereqs
- Python 3.11+ (3.12 recommended)
- A Telegram bot token via [@BotFather](https://t.me/BotFather)
- API keys: [Kimi (Moonshot)](https://platform.kimi.ai/console/api-keys), [fal.ai](https://fal.ai/dashboard/keys), [Pinata](https://app.pinata.cloud/developers/api-keys)
- A Base Sepolia wallet with a few drops of testnet ETH (free from [Coinbase faucet](https://www.coinbase.com/faucets/base-ethereum-sepolia-faucet))

### Install
```bash
git clone https://github.com/dream0x/Hermes-Tarot.git
cd Hermes-Tarot
cp .env.example .env       # then fill in real keys — see .env.example
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# (one-time, ~$1 in fal.ai credits) pre-render the 22 Major Arcana into the cache
python -m tarot.render --prewarm-major

# (one-time, free) deploy your own NFT contract
python -m nft.mint --deploy

# Run as a Hermes skill (drop into Hermes' skill dir):
ln -s "$(pwd)" ~/.hermes/skills/mnemos
hermes restart

# Or run the standalone Telegram bot:
python bot.py
```

### Production (Hetzner VPS, what we run)
```bash
# As root, on a fresh Ubuntu 24.04 VPS:
curl -fsSL https://raw.githubusercontent.com/dream0x/Hermes-Tarot/main/scripts/install_hetzner.sh -o /tmp/install.sh && bash /tmp/install.sh
# Then nano /opt/hermes-tarot/.env, paste secrets, and:
systemctl start hermes-tarot
```

### Smoke tests
```bash
python tarot/deck.py --validate                   # asserts 78 cards, no dupes
python kimi.py --ping                             # round-trips Kimi K2.6
python -m tarot.render --test the-fool --force    # one FLUX render
python -m nft.mint --dry-run                      # Pinata + tx simulation
python kimi.py --demo-reading                     # full sample reading
python scripts/smoke_test.py                      # all 5 services in one go
```

---

## Powered by

- [**Hermes Agent**](https://hermes-agent.nousresearch.com/) by Nous Research — persistent-memory agent runtime
- [**Kimi K2.6**](https://www.kimi.com/ai-models/kimi-k2-6) by Moonshot AI — 256K context, OpenAI-compatible API, agent swarm
- [**FLUX**](https://blackforestlabs.ai/) by Black Forest Labs — image generation via fal.ai
- [**Base**](https://base.org/) Sepolia testnet — gas-free ERC-721 mint
- [**Pinata**](https://www.pinata.cloud/) — IPFS pinning

---

## Roadmap (post-hackathon v0.3)
- Live **x402** paid premium readings (autonomous USDC microtransactions per spread)
- Autonomous mint per reading (every spread auto-mints as a private NFT keepsake)
- Discord & WhatsApp deployments (Hermes makes this ~30 min of config)
- Voice replies via TTS for blind users
- Mobile-friendly Telegram WebApp for richer card flips
- More spreads (Celtic Cross, Year-Ahead, Career Cross)
- Astrology natal chart rendering (skyfield is already in deps)
- Optional opt-in "predictions tracked" — Mnemos revisits old readings and asks if they came true

---

## License
MIT — see `LICENSE`. The live public bot may be offline after hackathon judging concludes; this code is reference and reproducible by anyone with their own API keys.
