# 🪞 Mnemos

> *the oracle that remembers every card it's ever pulled for you*

A divination companion built as a [Hermes Agent](https://hermes-agent.nousresearch.com/) skill. Mnemos pulls tarot spreads, paints the cards in a unified deck style with FLUX, and answers your question through them with **Kimi K2.6's 256K context** - using the entire history of readings it's ever given you. The hero card of each reading can be minted on **Base Sepolia** as an ERC-721 keepsake, viewable through a custom on-chain viewer.

> **Try it live:** [@mnemos_oracle_bot](https://t.me/mnemos_oracle_bot) on Telegram
> **View any minted card:** [the on-chain viewer](https://dream0x.github.io/Mnemos/?contract=0xa1b9bdeb72aa4f4b86c11234ea6301daa68d2c16&token=1)
>
> Public users get 3 readings/day (anti-abuse). Owner has unlimited use and minting.

Built for the [**Hermes Agent Creative Hackathon**](https://hermes-agent.nousresearch.com/) by [Nous Research](https://nousresearch.com/) × [Kimi (Moonshot AI)](https://www.kimi.com/), May 2026.

> **Status (May 2026, post-hackathon):** Submission complete. Bot is still live, real readings keep happening, code stays open. If the live bot goes offline later, you can self-host with your own API keys in ~10 min (see Setup below).

---

## Why this exists

The Hermes Agent ecosystem already has skills for FLUX images, Spotify playback, autonomous novel writing, and TouchDesigner. There was no skill for the **divination / personalization / spiritual companion** space - a category with massive Western mainstream traction (Co-Star: 30M users, WitchTok: billions of views).

Mnemos fills that gap and demonstrates Hermes' three real superpowers in one product:

| Hermes Agent strength | How Mnemos uses it |
|---|---|
| **Persistent memory** | Every reading is appended to a per-user JSONL; every new reading injects up to 30 prior readings into Kimi's 256K context - the oracle *literally remembers every card you've ever pulled* |
| **Scheduled tasks** (natural-language cron) | One tap on `📅 Daily at 9 AM UTC` registers a recurring job - your sun-sign horoscope arrives every morning, forever |
| **Multi-platform** | The same `oracle.py` skill runs through any Hermes transport - Telegram is the first; Discord/Slack/WhatsApp would need ~30 min of config, no code changes |

It also showcases **Kimi K2.6's 256K context** as a personalization engine, not just a long-doc reader.

---

## What makes a Mnemos reading different

Most chatbot tarot readers do one of two things: (a) describe each card in the abstract, or (b) generate a generic "you are entering a transformative phase" blob. Mnemos is engineered to do neither.

The system prompt forces a specific shape on every reading:

1. **Frame** - restate the question in one sentence that names *what kind* of question it is (timing? trust? readiness?). Show the user you heard them.
2. **Cards as answer** - one paragraph per card. Each paragraph translates the card's archetype into a concrete answer for *this* user's *specific* situation. No textbook recitation.
3. **Direction** - the final paragraph delivers a single, soft instruction. Not a prediction; a stance to hold. Ends with a body image (breath, posture, footing).
4. **Memory call-back** - when relevant, the reading references your prior readings ("Last week the Magician came to you - that cycle is closing now"). At most one per session.

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
| `oracle.py` | Public skill API - pull / render / interpret / mint / save |
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
git clone https://github.com/dream0x/Mnemos.git
cd Mnemos
cp .env.example .env       # then fill in real keys - see .env.example
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
curl -fsSL https://raw.githubusercontent.com/dream0x/Mnemos/main/scripts/install_hetzner.sh -o /tmp/install.sh && bash /tmp/install.sh
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

## How Mnemos uses Hermes Agent

Mnemos is structured as a first-class **Hermes Agent skill**, not a standalone app that happens to wrap an LLM. Three things make this real:

**1. The skill manifest (`SKILL.md`)** follows the [agentskills.io](https://agentskills.io) standard. When you drop the project into `~/.hermes/skills/mnemos`, Hermes auto-discovers it from the YAML frontmatter (`name`, `version`, `description`, `runtime`) and loads the tool surface declared in the markdown body. The agent can then invoke Mnemos from natural language ("pull cards on this", "give me my horoscope") without any user-side wiring.

**2. The skill API (`oracle.py`)** exposes a flat set of tools designed to be agent-callable, not user-callable. Each function takes plain JSON-serializable arguments and returns plain dicts:

| Tool | Returns | When the agent calls it |
|---|---|---|
| `pull_cards(user_id, question, spread)` | `{question, spread, cards: [...]}` | User asks for a reading |
| `render_cards(cards)` | cards with `image_path` filled | Always after `pull_cards` |
| `interpret_reading(user_id, question, cards, spread)` | string | After cards are rendered |
| `daily_horoscope(sign, user_id)` | string | "what's my horoscope today" |
| `set_profile(user_id, **fields)` | profile dict | "I'm a Pisces" |
| `recall_history(user_id, limit)` | list of past readings | "what cards did I get last week" |
| `mint_card(user_id, reading_id, card_index, to_address)` | mint result with token id + viewer URL | "mint that one on-chain" |

The Telegram bot in `bot.py` is just *one* transport that calls these tools. The same module, dropped into a Hermes-with-Discord install, works untouched.

**3. The persistent-memory pattern** is Hermes' signature feature, and Mnemos leans into it hard. Hermes itself uses `~/.hermes/MEMORY.md` + `~/.hermes/USER.md` for global agent memory. Mnemos adds *skill-scoped* memory underneath: per-user JSONL files at `data/{telegram_user_id}/readings.jsonl` plus `profile.json`. Every reading is appended; every new reading reads the tail back into the prompt. Hermes' built-in scheduler is what powers the daily-horoscope cron — when the user taps `📅 Daily at 9 AM UTC`, we register a recurring job whose handler simply calls `oracle.daily_horoscope()` and DM's the result. No custom cron service needed.

> The result: Mnemos is the kind of skill that actually *grows with you*. The same skill instance, used over weeks, references your real history. That's a Hermes-shaped product, not a one-shot LLM call dressed up.

---

## How Mnemos uses Kimi K2.6

Kimi K2.6 (Moonshot AI's 1T-parameter MoE) is the **interpretation engine**. We hit it through the OpenAI-compatible endpoint at `https://api.moonshot.ai/v1`, model id `kimi-k2.6`. Every Mnemos reading and every horoscope is a Kimi call. Three implementation choices matter:

**1. The 256K context window is the literal product mechanic.** A typical 3-card reading sends Kimi:
- The locked persona (~1.5K tokens, see `kimi.py::_SYSTEM_PROMPT`)
- One few-shot example demonstrating tone and form (~1K tokens)
- The user's full profile JSON (sun sign, birth place, wallet, …)
- **Up to the last 30 readings, weighed by recency** (`memory.py::context_snapshot`, capped at 60K chars / ~15K tokens with oldest-first truncation)
- The current question and freshly-drawn cards

That's typically 5-20K input tokens, well under the 256K ceiling. The result: Mnemos can naturally reference last week's pull ("the Magician walked behind you then; the Tower turning now is its echo") without any retrieval-augmentation pipeline. We just put the history in the context, and Kimi notices what matters.

**2. `thinking: disabled` for warm immediate prose.** K2.6 ships with a "thinking" reasoning mode that emits chain-of-thought tokens to a separate field. For a divination tone we want the *first* response to be the final response — no inner monologue, no scaffolding, no apologetic preamble. We pass `extra_body={"thinking": {"type": "disabled"}}` on every chat completion (see `kimi.py::_chat`). This roughly halves latency too.

**3. A locked output shape with belt-and-suspenders.** The system prompt enforces a strict 4-paragraph form: *frame the question → cards as direct answer → concrete direction → close on a body image*, plus a one-line italic disclaimer. It also explicitly forbids em-dashes (a model tic) and lists 8 phrases to never use ("I sense", "trust your gut", etc.). On top of that, `kimi.py::_strip_dashes` post-processes every response to replace any em/en-dash that slips through with a comma or hyphen. The output is reliably plain prose ready to ship straight to Telegram.

**Cost**: ~$0.30 per 1M input tokens, ~$2.50 per 1M output. A 3-card reading averages ~5K input + ~700 output ≈ $0.0033. The daily $5 spend ceiling in `ratelimit.py` covers ~1500 readings before the kill switch trips.

---

## Other infrastructure

- [**FLUX [dev]**](https://blackforestlabs.ai/) by Black Forest Labs (via [fal.ai](https://fal.ai)) - card image generation. ~$0.025/image, 4-5s per call. We pre-render all 22 Major Arcana into a disk cache so demo readings are instant; only Minor Arcana cards trigger a fresh render. A Pillow post-process overlays the correct card title in EB Garamond serif (FLUX hallucinates fake titles, so we always overwrite them) and rotates 180° for reversed cards.
- [**Base Sepolia**](https://base.org/) - gas-free L2 testnet for the ERC-721 mint. Contract is a single-file 200-line ERC-721 (no OpenZeppelin imports, ships with the repo), pre-compiled artifact at `nft/build/OracleCard.json` so the production server never invokes solcx.
- [**Pinata**](https://www.pinata.cloud/) - IPFS pinning for card images and ERC-721 metadata JSON. Free tier comfortably covers hackathon traffic.
- [**Hetzner CX22**](https://www.hetzner.com/cloud) - €4.5/mo VPS running the bot under systemd (auto-restart, ufw firewall, hardened with `NoNewPrivileges`, `ProtectSystem=full`, `ProtectHome=read-only`).

---

## Roadmap (post-hackathon v0.3)
- Live **x402** paid premium readings (autonomous USDC microtransactions per spread)
- Autonomous mint per reading (every spread auto-mints as a private NFT keepsake)
- Run on a real **Hermes Agent runtime** (current production is `bot.py` calling `oracle.py` directly; the SKILL.md surface is ready, just needs the agent installed alongside)
- Discord & WhatsApp deployments
- Voice replies via TTS
- More spreads (Celtic Cross, Year-Ahead, Career Cross)
- Astrology natal chart rendering (skyfield is already in deps)
- Persistent JobQueue (currently in-memory, daily horoscopes are lost on restart)
- Optional opt-in "predictions tracked" - Mnemos revisits old readings and asks if they came true

---

## What I learned building this

A few things that surprised me and might help anyone else building on top:

- **Kimi K2.6's 256K context is *the* product mechanic, not a footnote.** Once you put 30 prior readings into every prompt, the model naturally weaves callbacks ("the Magician walked behind you last week — that cycle is closing"). No retrieval, no embeddings, no vector DB. Just full conversation history. A wrapper-style "tarot bot" would never get this texture.
- **FLUX [dev] still hallucinates titles on cards.** Even with strong negative prompts. The fix is `Pillow` overlaying the real card name in EB Garamond on top of the bottom band — clean, fast, free. Style locking happens through a single shared `DECK_STYLE` prompt + per-card art fragment.
- **OpenSea retired all testnets** in 2025, so for a hackathon NFT mint you now need a custom viewer. The `docs/index.html` is one HTML file that reads the contract via Base Sepolia RPC and pulls metadata from IPFS — works in any browser, no backend.
- **Telegram's `ReplyKeyboardMarkup` beats `InlineKeyboard` for primary navigation.** Persistent buttons at the bottom are way more discoverable than slash commands or inline-only flows.
- **`fcntl.flock` for state files matters even at 10 users.** With `asyncio.to_thread` plus concurrent readings, two parallel updates to `quota.json` or `readings.jsonl` can lose data. Cheap fix, big robustness win.
- **Don't trust a price constant you derived once.** Mid-hackathon code audit found that the Kimi cost tracker was off by 1000× — the `$5/day` ceiling would only have triggered at $5000 of real spend. Lesson: write a sanity unit test that asserts "one typical reading costs ~$X".

---

## License
MIT - see `LICENSE`. If the live public bot ever goes offline, this repo is fully reproducible — clone, copy `.env.example` to `.env`, fill your own API keys, and run.
