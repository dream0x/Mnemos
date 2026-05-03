# Mnemos — Hackathon Submission

> Internal cheat sheet for the user. Not pushed for marketing — just keeps everything you need in one place when you record + post.

## ✅ Status (live)

- **Code:** https://github.com/dream0x/Hermes-Tarot — public, MIT
- **Live bot:** [@hermeskimi_oracle_bot](https://t.me/hermeskimi_oracle_bot) on Telegram
- **NFT contract (Base Sepolia):** `0xA1b9BdEB72aA4F4B86C11234ea6301DaA68D2C16` — [Basescan](https://sepolia.basescan.org/address/0xA1b9BdEB72aA4F4B86C11234ea6301DaA68D2C16)
- **Custom on-chain card viewer:** https://dream0x.github.io/Hermes-Tarot/?contract=0xa1b9bdeb72aa4f4b86c11234ea6301daa68d2c16&token=1
- **Hosting:** Hetzner CX22 (€4.5/mo), systemd auto-restart, ufw firewall

## Demo recording — must-show beats

In any order, but all four must appear in the 60–90s video:

1. **A reading happens** — type a question in @hermeskimi_oracle_bot, three FLUX cards appear as a media-group, Kimi reading scrolls below.
2. **Memory is real** — pull a SECOND reading and show that the oracle references the first ("Last week the Fool came to you…"). This is the "Powered by Kimi K2.6 · 256K context" moment — burn that caption on screen.
3. **Mint on-chain** — tap the `🔮 Mint` button, see the OpenSea-style custom viewer load the actual card from Base Sepolia + IPFS. (Use this URL: https://dream0x.github.io/Hermes-Tarot/?contract=0xa1b9bdeb72aa4f4b86c11234ea6301daa68d2c16&token=N)
4. **Schedule daily** — tap `📅 Daily at 9 AM UTC` to show Hermes' natural scheduling power.

**On-screen credits required:** `@NousResearch` `@Kimi_Moonshot`, plus the GitHub URL on the end card.

---

## ✍️ Tweet must-haves (you write the copy)

Required in the actual tweet text or media:
- [ ] Tags `@NousResearch`
- [ ] Tags `@Kimi_Moonshot`
- [ ] Demo video attached (vertical 9:16 if you can)
- [ ] GitHub URL: `github.com/dream0x/Hermes-Tarot`
- [ ] Some hook that names what's special. Concrete pitches you can riff on:
  - "An AI tarot reader that remembers every card it has ever pulled for you. Built on @NousResearch's Hermes Agent + @Kimi_Moonshot's K2.6 256K context. Mints your hero card on Base Sepolia."
  - "I taught Hermes Agent to read tarot. It paints the cards itself, writes the reading with Kimi K2.6, and mints your card on-chain."
  - "What if your daily horoscope remembered every reading you ever had? Mnemos: tarot + astro + on-chain keepsakes, in your DMs."

Optional but adds polish:
- Mention `Base Sepolia` (judges in crypto-AI space will notice)
- Mention `Built in 24h for the Hermes Creative Hackathon`
- Link to live bot: `t.me/hermeskimi_oracle_bot`

---

## 📩 Discord post (drop in `#creative-hackathon-submissions`)

Two options — pick one or remix:

### Short
```
🔮 Mnemos — a tarot/astrology divination skill for Hermes Agent.
Pulls 3-card spreads rendered as a unified FLUX deck, interprets via Kimi K2.6
with 256K-context memory of every prior reading, and mints the hero card on
Base Sepolia. Live bot: @hermeskimi_oracle_bot.

Tweet: <YOUR_TWEET_URL>
GitHub: https://github.com/dream0x/Hermes-Tarot
```

### Long (for the writeup track judges)
```
🔮 Mnemos

Built a Hermes Agent skill that turns the agent into a personal divination
companion. It pulls tarot spreads, renders the cards via FLUX in a single
unified deck style, interprets the reading with Kimi K2.6, and remembers
every reading you've ever had thanks to K2.6's 256K context. The hero card
of any reading mints as an ERC-721 on Base Sepolia, viewable through a
custom on-chain card viewer (since OpenSea retired testnets last year).

Why this leans on Hermes' unique strengths:
  • Persistent memory: per-user JSONL fed back into K2.6 every reading
  • Natural-language scheduling: one tap → daily horoscope at 9 AM UTC
  • Multi-platform: Telegram first, same skill works on Discord/Slack/WhatsApp

Why it's a Kimi-Track submission:
  • K2.6's 256K context is the literal product mechanic, not a feature flag
  • thinking-mode disabled for warm immediate prose
  • Multilingual auto-detect (locked to English output by design)

Live bot: https://t.me/hermeskimi_oracle_bot
Tweet: <YOUR_TWEET_URL>
GitHub (MIT): https://github.com/dream0x/Hermes-Tarot
Card viewer: https://dream0x.github.io/Hermes-Tarot/
Contract: 0xA1b9BdEB72aA4F4B86C11234ea6301DaA68D2C16 (Base Sepolia)
```

---

## 🧹 Post-hackathon cleanup checklist

When judging is over (don't forget — chat already exposed these):

- [ ] Rotate `KIMI_API_KEY` (platform.kimi.ai → API Keys → Revoke + Create new)
- [ ] Rotate `FAL_KEY` (fal.ai/dashboard/keys)
- [ ] Rotate `PINATA_JWT` (app.pinata.cloud → API Keys)
- [ ] Revoke Telegram bot token via @BotFather → `/revoke` (or just stop the service if you want to keep the bot for fun)
- [ ] Drain & abandon the Base Sepolia wallet (`0x293e3ADa1dF0E3a09Dd332E0a29476cc322c2919`) — testnet only so impact is zero, but rotate hygiene
- [ ] Optionally `hcloud server delete <id>` to retire the Hetzner box (or keep for €4.5/mo if the bot is fun)
- [ ] Update README to add a "live bot offline" note if you take the bot down
