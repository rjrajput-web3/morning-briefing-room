# Morning Briefing Room

**Track 02 — Best Personal/Creative Workflow** · Flip the Switch Hackathon (WeMakeDevs × Switch AI × DevTools Academy)

A custom Switch agent that turns a team-chat room into a personal morning briefing: every morning it posts crypto prices, deadline countdowns, and tech headlines, then answers follow-up questions in-thread with running memory — an AI agent and a person finishing a real daily task together, inside Switch.

## The problem

Mornings start with 15 minutes of tab-hopping: check BTC/ETH, scan headlines, recount days until each deadline. It's repetitive, forgettable, and never in one place.

## The solution

One Switch room. Every morning at 08:00 IST the **briefing-room** agent posts:

- 📊 **Crypto watchlist** — BTC, ETH, SOL, NEAR spot prices (Coinbase public API, no key)
- ⏳ **Deadline countdowns** — days remaining for each tracked deadline (configurable)
- 📰 **Headlines** — latest from CoinDesk, CoinTelegraph, TechCrunch (free RSS)

Then it **stays in the room**: ask "what's the SOL price?" or "how many days until the NEAR deadline?" and it answers from that morning's data, remembering the week's briefings and Q&A. No invented numbers — if the data isn't there, it says so.

## How it works

```
Switch (switch-core)            Morning Briefing Room agent (this repo)
┌──────────────────┐            ┌──────────────────────────────────────┐
│ room: morning-   │  SSE down  │  scheduler (08:00 IST)                │
│ briefing-room    │◄───────────┤  briefing composer (template +        │
│                  │  HTTP up   │   best-effort LLM polish)             │
│  user ──message──┼───────────►│  Q&A handler (LLM answer, validated;  │
│         ◄─reply──┼────────────┤   deterministic data fallback)        │
└──────────────────┘  2s beat  │  running memory (JSON: briefings,     │
                               │   prefs, Q&A log)                     │
                               └──────────────────────────────────────┘
```

- **Wire protocol**: the agent speaks Switch's documented agent protocol — one SSE event stream down, HTTP up, client-generated connection id reused across reconnects, 2-second heartbeat (6s TTL).
- **Reliability first**: the briefing is a deterministic template over live data — it posts even when the free LLM quota is exhausted. LLM polish (Gemini free tier) is applied only if the output passes a strict validator (the free models sometimes "think out loud"); otherwise the clean template ships.
- **Honest Q&A**: answers come from that morning's briefing data. Price/deadline/news intents are answered deterministically; anything else gets an honest "I don't have that" rather than a hallucination.
- **Human pacing**: 2–6s randomized pauses between actions, so room activity reads naturally.
- **Zero paid dependencies**: Python stdlib only. Data from free public APIs/RSS. LLM via free tiers only.

## Setup

### 1. Run Switch

Use the official standalone deployment ([sandbox-quantum/switch](https://github.com/sandbox-quantum/switch), `standalone-compose`):

```bash
git clone https://github.com/sandbox-quantum/switch
# follow its self-host docs to bring up the gateway (API on :8000)
```

Note your `AGENT_REGISTRATION_TOKEN`.

### 2. Register the agent and create the room

```bash
export SWITCH_API=http://localhost:8000
export AGENT_REGISTRATION_TOKEN=<token>
python3 scripts/register.py   # registers "briefing-room", creates the room,
                              # saves agent id + api key to agent-state.json (gitignored)
```

### 3. Run the agent

```bash
python3 -m agent.agent            # daemon: scheduler + SSE listener + heartbeat
python3 -m agent.agent --briefing-now                      # post today's briefing immediately
python3 -m agent.agent --simulate-question "NEAR price?"   # exercise the Q&A path
```

The agent reads `agent-state.json` (agent id, api key, room id) created by the register script. State and memory files are gitignored — never commit keys.

### Configuration

Edit `agent/config.py`: briefing time/timezone, watchlist symbols, RSS feeds, deadlines, model preference.

## Demo

📹 Demo video: https://github.com/rjrajput-web3/morning-briefing-room/releases/download/demo-v1/morning-briefing-room-demo.mp4
*(95s — recorded against a live local Switch deployment)*

What it shows:
1. The agent daemon starting and opening its SSE stream.
2. The morning briefing landing in the `morning-briefing-room` with live prices, real countdowns, real headlines.
3. A follow-up question asked in the room and the agent answering from that morning's data.
4. The room history proving the full loop.

## Project structure

```
agent/
  agent.py          daemon: scheduler, SSE event handling, Q&A
  switch_client.py  wire-protocol client (SSE stream, 2s heartbeat, HTTP ops)
  briefing.py       briefing composer (template + validated LLM polish)
  data_sources.py   Coinbase spot prices + RSS news (free, no keys)
  llm.py            free-tier Gemini route with model fallback + echo validator
  memory.py         running memory: per-day briefings, prefs, Q&A log
  config.py         schedule, watchlist, feeds, deadlines
scripts/
  register.py       one-time setup: register agent + create room
```

## Originality

All code in `agent/` was written for this hackathon against Switch's public agent-protocol documentation. It is not a redeployed official example. The briefing template, Q&A fallback logic, echo validator, and pacing are original to this project.

## License

MIT — see [LICENSE](LICENSE).
