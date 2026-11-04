"""Morning briefing composer: data -> (LLM-polished | template) text."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from . import config, data_sources, llm


def _deadline_lines(today):
    lines = []
    for label, iso in config.DEADLINES:
        try:
            d = date.fromisoformat(iso)
            delta = (d - today).days
            if delta < 0:
                lines.append(f"- {label}: passed ({iso})")
            elif delta == 0:
                lines.append(f"- {label}: TODAY")
            else:
                lines.append(f"- {label}: {delta} day(s) left ({iso})")
        except ValueError:
            lines.append(f"- {label}: {iso}")
    return lines


def _template_briefing(prices, news, deadline_lines, today_str):
    parts = [f"\u2600\ufe0f Morning Briefing \u2014 {today_str}\n"]
    parts.append("\U0001f4ca Crypto watchlist (USD, Coinbase spot):")
    if prices:
        for sym, px in prices.items():
            parts.append(f"  \u2022 {sym}: ${px:,.2f}")
    else:
        parts.append("  (price feed unreachable this morning)")
    parts.append("\n\u23f3 Deadline countdowns:")
    parts.extend(deadline_lines)
    parts.append("\n\U0001f4f0 Headlines:")
    if news:
        for n in news:
            parts.append(f"  \u2022 [{n['source']}] {n['title']}")
    else:
        parts.append("  (news feeds unreachable this morning)")
    parts.append("\nReply here with any follow-up question \u2014 I remember "
                 "this week's briefings.")
    return "\n".join(parts)


def compose(today=None):
    """Build today's briefing text. Returns (text, used_llm, raw_data)."""
    today = today or datetime.now(ZoneInfo(config.TIMEZONE)).date()
    today_str = today.strftime("%A, %d %B %Y")
    prices = data_sources.get_prices()
    news = data_sources.get_news()
    deadline_lines = _deadline_lines(today)
    raw_data = {
        "date": today.isoformat(),
        "prices": prices,
        "news": [{"title": n["title"], "source": n["source"]} for n in news],
        "deadlines": deadline_lines,
    }

    template = _template_briefing(prices, news, deadline_lines, today_str)

    # Conversational prompt — this model echoes structured instruction
    # lists, so the request is phrased as plain prose.
    prompt = (
        "Here is this morning's raw briefing data. Please write it up as "
        "a short, skimmable briefing message for a crypto builder in "
        "India — under 220 words, plain text, keep every number and "
        "headline exactly as given, keep the deadline countdowns, a few "
        "emojis are fine, and end with one short line inviting follow-up "
        "questions. Just write the briefing:\n\n" + template
    )
    polished, model = llm.ask(prompt, max_tokens=600)
    if polished and llm.looks_clean(polished, must_contain="Morning Briefing"):
        print(f"[briefing] LLM polish accepted ({model})")
        return polished.strip(), True, raw_data
    if polished:
        print(f"[briefing] LLM output rejected as echo ({model}), using template")
    return template, False, raw_data
