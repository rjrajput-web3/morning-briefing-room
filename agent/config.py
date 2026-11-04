"""Static configuration for the Morning Briefing Room agent."""
import os

# Switch server (self-hosted switch-core)
SWITCH_API = os.environ.get("SWITCH_API", "http://127.0.0.1:8000")
STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "agent-state.json")

# Briefing schedule — 08:00 Asia/Kolkata every day
BRIEFING_HOUR_IST = 8
BRIEFING_MINUTE_IST = 0
TIMEZONE = "Asia/Kolkata"

# Crypto watchlist (Coinbase spot symbols)
WATCHLIST = ["BTC", "ETH", "SOL", "NEAR"]

# Free RSS news feeds (no scraping of paywalled sites)
NEWS_FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss"),
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
]
NEWS_PER_FEED = 2

# Deadline countdowns: (label, date). Dates are calendar dates; the agent
# computes days remaining at briefing time.
DEADLINES = [
    ("Flip the Switch hackathon submission", "2026-11-07"),
    ("NEAR 'Build Beyond Boundaries' submission", "2026-11-14"),
    ("Code for a Billion submission", "2026-11-15"),
]

# Free LLM route: Gemini helper (Zro free budget was exhausted at build time)
GEMINI_HELPER = os.path.expanduser(
    "~/workspace/custom-connectors/custom.gemini/bin/gemini.py"
)
GEMINI_MODEL = "gemma-4-26b-a4b-it"

# Human pacing: random pause range (seconds) between actions
PACE_MIN = 2.0
PACE_MAX = 6.0

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")
