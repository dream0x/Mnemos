# 🔮 Hermes Oracle

> A Hermes Agent skill that turns the agent into a personal divination companion: tarot spreads rendered as a visually consistent FLUX deck, interpreted by Kimi K2.6's 256K context with full memory of your past readings, and delivered on schedule via Telegram. The hero card of each reading mints as an ERC-721 NFT on Base Sepolia.

Built for the [**Hermes Agent Creative Hackathon**](https://hermes-agent.nousresearch.com/) by [Nous Research](https://nousresearch.com/) × [Kimi (Moonshot AI)](https://www.kimi.com/), May 2026.

> **Try it live:** [@hermeskimi_oracle_bot](https://t.me/hermeskimi_oracle_bot) on Telegram · **View any minted card:** [the on-chain viewer](https://dream0x.github.io/Hermes-Tarot/?contract=0xa1b9bdeb72aa4f4b86c11234ea6301daa68d2c16&token=1)
>
> Public users get 3 readings/day (anti-abuse). Owner has unlimited use and minting.

![demo](docs/demo.gif) <!-- replaced with the submission video before final -->

---

## Why this exists

The Hermes Agent ecosystem (see `awesome-hermes-agent`) already has skills for FLUX images, Spotify playback, autonomous novel writing, and TouchDesigner. There was no skill for the **divination / personalization / spiritual companion** space — a category with massive Western mainstream traction (Co-Star: 30M users, WitchTok: billions of views).

Hermes Oracle fills that gap and demonstrates three Hermes-unique strengths in one product:
- **Persistent memory** → every reading you've ever had is in context for the next one
- **Scheduled cron in natural language** → daily horoscope DM at 9 AM
- **Multi-platform** → lives where you already chat (Telegram first, Discord/Slack trivial)

It also showcases **Kimi K2.6's 256K context window** as a personalization engine, not just a long-doc reader.

---

## Architecture

```
┌─ Telegram ───────────────────────────┐
│  user message                        │
└──────────────┬───────────────────────┘
               │
        ┌──────▼──────┐    rate limit + spend ceiling
        │  Hermes     │───►│ ratelimit.py + config.py │
        │  Agent      │
        └──────┬──────┘
               │
   ┌───────────┼─────────────┬──────────────┐
   ▼           ▼             ▼              ▼
┌──────┐  ┌─────────┐   ┌──────────┐  ┌──────────┐
│ tarot│  │ astro   │   │  Kimi    │  │ memory   │
│ deck │  │ natal/  │   │  K2.6    │  │ MEMORY.md│
│  +   │  │ daily   │   │ (256K)   │  │ JSONL    │
│ FLUX │  │         │   │          │  │ history  │
└──┬───┘  └─────────┘   └──────────┘  └──────────┘
   │
   ▼ on "mint"
┌──────────────────┐
│ Pinata (IPFS)    │
│ → Base Sepolia   │
│   ERC-721        │
└──────────────────┘
```

---

## Setup

### Prereqs
- Python 3.11+
- [Hermes Agent](https://hermes-agent.nousresearch.com/) installed (`curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash` then `hermes setup`)
- [Foundry](https://book.getfoundry.sh/) (only if you want to redeploy the contract)

### Install
```bash
git clone https://github.com/dream0x/Hermes-Tarot.git
cd Hermes-Tarot
cp .env.example .env       # then fill in real keys — see .env.example for source URLs
pip install -r requirements.txt
ln -s "$(pwd)" ~/.hermes/skills/Hermes-Tarot
hermes restart
```

In your Hermes chat:
```
/skills
# you should see Hermes-Tarot listed

pull cards for my week, focus on work
```

### Smoke tests
```bash
python -m hermes_oracle.tarot.deck --validate     # asserts 78 cards, no dupes
python -m hermes_oracle.kimi --ping               # round-trips Kimi
python -m hermes_oracle.tarot.render --test fool  # one FLUX image
python -m hermes_oracle.nft.mint --dry-run        # Pinata + tx simulation
```

---

## Powered by
- [**Hermes Agent**](https://hermes-agent.nousresearch.com/) by Nous Research
- [**Kimi K2.6**](https://www.kimi.com/ai-models/kimi-k2-6) by Moonshot AI (256K context)
- [**FLUX**](https://blackforestlabs.ai/) by Black Forest Labs (via fal.ai)
- [**Base**](https://base.org/) Sepolia testnet

---

## What this demonstrates

| Hermes Agent strength | How Hermes Oracle uses it |
|---|---|
| Persistent memory | Every reading is appended to a per-user JSONL; every new reading injects the full history into Kimi's 256K context — the oracle *literally remembers every card you've ever pulled* |
| Scheduled tasks (natural-language cron) | One tap on `📅 Daily at 9 AM UTC` registers a JobQueue cron — your sun-sign horoscope arrives every morning, forever |
| Multi-platform | The same `oracle.py` skill module runs through any Hermes transport — Telegram is just the first; Discord/Slack/WhatsApp would need ~30 min of config, no code changes |
| Skills that grow | Add reversed-card art, new spreads, custom decks — the skill model lets the agent *learn what you ask for* and adapt without retraining |

## Powered by Kimi K2.6

The **Kimi Track** rewards genuine use of Kimi K2.6, not a thin wrapper. Hermes Oracle uses K2.6 specifically for:

- **256K context window** — the entire reading history fits, every time. Older models would have to summarize, losing texture.
- **Long-horizon coherence** — the oracle voice stays in character across many turns, with stable archetypes and tone.
- **Multilingual** — auto-detects user input language and translates in voice (we lock to English output by design).
- **`thinking: disabled`** — for warm, immediate prose without chain-of-thought leakage.

## Roadmap (post-hackathon v0.2)
- Live **x402** paid premium readings (autonomous USDC microtransactions per spread)
- Autonomous mint per reading (every spread auto-mints as a private NFT keepsake)
- Discord & WhatsApp deployments (Hermes makes this ~30 min of config)
- Voice replies via TTS
- Mobile-friendly Telegram WebApp for richer card flips & spread choices
- More spreads (Celtic Cross, Year-Ahead, Career Cross)
- Astrology natal chart rendering (skyfield is already in deps)
- Optional opt-in “predictions tracked” — agent revisits old readings and asks if they came true

---

## License
MIT — see `LICENSE`.

The live public bot may be offline after hackathon judging concludes; this code is reference and reproducible by anyone with their own API keys.
