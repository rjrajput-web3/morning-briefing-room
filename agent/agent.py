#!/usr/bin/env python3
"""Morning Briefing Room agent — main daemon.

- Posts a scheduled morning briefing (08:00 IST) to the Switch room.
- Listens on the SSE event stream and answers follow-up questions in
  the room, with running memory (per-day briefings + Q&A log).
- Human pacing: 2-6s random pauses between actions.

Usage:
    python3 -m agent.agent [--briefing-now] [--simulate-question "..."]
    (run from work/ so the relative imports resolve)
"""
import json
import os
import random
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import briefing, config, llm, memory  # noqa: E402
from agent.switch_client import EventStream, SwitchClient  # noqa: E402


def pace():
    time.sleep(random.uniform(config.PACE_MIN, config.PACE_MAX))


def load_state():
    with open(config.STATE_FILE) as f:
        return json.load(f)


class BriefingAgent:
    def __init__(self):
        state = load_state()
        self.client = SwitchClient(
            config.SWITCH_API, state["agent_id"], state["api_key"]
        )
        self.room_id = state["room_id"]
        self.mem = memory.load()
        # Hashes of our own recent posts — the room echoes our messages back
        # on the event stream, and we must not answer ourselves.
        self._own_hashes = {}  # md5(body) -> timestamp
        print(f"[agent] room={self.room_id}")

    def _remember_own(self, body):
        import hashlib
        self._own_hashes[hashlib.md5(body.encode()).hexdigest()] = time.time()
        # prune entries older than 30 min
        cutoff = time.time() - 1800
        self._own_hashes = {h: t for h, t in self._own_hashes.items()
                            if t > cutoff}

    def _is_ours(self, body):
        import hashlib
        return hashlib.md5(body.encode()).hexdigest() in self._own_hashes

    # ---- briefing ----

    def today_str(self):
        return datetime.now(ZoneInfo(config.TIMEZONE)).date().isoformat()

    def briefing_due(self):
        now = datetime.now(ZoneInfo(config.TIMEZONE))
        slot = now.hour * 60 + now.minute
        target = config.BRIEFING_HOUR_IST * 60 + config.BRIEFING_MINUTE_IST
        return slot >= target and self.today_str() not in self.mem["briefings"]

    def post_briefing(self):
        print("[agent] composing briefing...")
        text, used_llm, raw_data = briefing.compose()
        pace()
        self.client.post_message(self.room_id, text)
        self._remember_own(text)
        memory.record_briefing(
            self.mem,
            self.today_str(),
            {"used_llm": used_llm, "chars": len(text), "data": raw_data},
        )
        print(f"[agent] briefing posted (llm={used_llm}, {len(text)} chars)")

    # ---- Q&A ----

    def handle_event(self, name, data):
        if name != "message":
            return
        payload = data.get("payload", data)
        sender = payload.get("sender", "")
        body = (payload.get("body") or "").strip()
        if not body or self._is_ours(body):
            return
        sender_name = payload.get("sender_name") or sender
        print(f"[agent] Q from {sender_name}: {body[:120]}")
        self.answer_question(body, sender_name)

    def answer_question(self, question, sender_name="you"):
        today = self.today_str()
        brief = self.mem["briefings"].get(today, {})
        data = brief.get("data", {})
        ctx_lines = []
        if data.get("prices"):
            px = ", ".join(f"{s} ${p:,.2f}"
                           for s, p in data["prices"].items())
            ctx_lines.append(f"Today's prices (USD): {px}.")
        for dl in data.get("deadlines", []):
            ctx_lines.append(dl)
        if data.get("news"):
            heads = "; ".join(
                f"[{n['source']}] {n['title']}" for n in data["news"][:6])
            ctx_lines.append(f"Today's headlines: {heads}")
        for qa in self.mem["qa_log"][-3:]:
            ctx_lines.append(f"Earlier Q: {qa['q'][:100]} / A: {qa['a'][:100]}")
        context = "\n".join(ctx_lines) if ctx_lines else "No briefing data yet today."
        # Plain conversational prompt — the model echoes structured
        # instruction lists, so keep it simple.
        prompt = (
            f"Here is this morning's briefing data:\n{context}\n\n"
            f"{sender_name} asks: {question}\n\n"
            "Reply as a helpful assistant in under 120 words, plain text. "
            "Use the briefing data above when relevant. If the answer isn't "
            "in the data, say so honestly — never invent numbers."
        )
        answer, model = llm.ask(prompt, max_tokens=400)
        if answer and llm.looks_clean(answer):
            print(f"[agent] LLM answer accepted ({model})")
        else:
            if answer:
                print(f"[agent] LLM answer rejected as echo ({model})")
            answer = self._template_answer(question, data)
        pace()
        self.client.post_message(self.room_id, answer)
        self._remember_own(answer)
        memory.record_qa(self.mem, question, answer)
        print(f"[agent] answered ({len(answer)} chars)")

    def _template_answer(self, question, data):
        """Deterministic data-driven answer when the LLM is unusable."""
        q = question.lower()
        prices = data.get("prices", {})
        parts = []

        # price intent (specific coin or whole watchlist)
        wants_price = any(w in q for w in ("price", "much", "worth", "rate"))
        for sym in ("BTC", "ETH", "SOL", "NEAR"):
            if sym.lower() in q and wants_price:
                if sym in prices:
                    parts.append(f"{sym} is at ${prices[sym]:,.2f} this "
                                 f"morning (Coinbase spot, USD).")
                else:
                    parts.append(f"I don't have a fresh {sym} price — the "
                                 f"price feed was unreachable this morning.")
                break
        else:
            if wants_price and prices:
                px = ", ".join(f"{s} ${p:,.2f}" for s, p in prices.items())
                parts.append(f"This morning's prices (USD): {px}.")

        # deadline intent
        if any(w in q for w in ("deadline", "days left", "due", "countdown",
                                "submission", "submit", "hackathon")):
            lines = data.get("deadlines") or []
            if lines:
                parts.append("Deadline countdowns:\n" + "\n".join(lines))
            else:
                parts.append("I don't have the deadline list handy — check "
                             "the briefing above.")

        # news intent
        if any(w in q for w in ("news", "headline", "happening")):
            news = data.get("news") or []
            if news:
                heads = "\n".join(
                    f"\u2022 [{n['source']}] {n['title']}" for n in news[:5])
                parts.append("Today's headlines:\n" + heads)
            else:
                parts.append("The news feeds were unreachable this morning.")

        if parts:
            return "\n\n".join(parts)
        # generic fallback — honest, saved for next briefing
        return (
            "Good question — I don't have a solid answer from this "
            "morning's data, and I won't guess. I've saved it and will "
            "cover it in tomorrow's briefing."
        )

    # ---- run ----

    def run(self, briefing_now=False):
        if briefing_now:
            self.post_briefing()
            return
        stream = EventStream(self.client, self.room_id, self.handle_event)
        stream.start()
        print("[agent] listening. Ctrl-C to stop.")
        try:
            while True:
                time.sleep(30)
                if self.briefing_due():
                    self.post_briefing()
        except KeyboardInterrupt:
            print("[agent] stopping...")
        finally:
            stream.stop()


def main():
    agent = BriefingAgent()
    args = sys.argv[1:]
    if "--simulate-question" in args:
        q = args[args.index("--simulate-question") + 1]
        print(f"[demo] simulated incoming question: {q}")
        agent.answer_question(q, sender_name="demo-user")
        return
    agent.run(briefing_now="--briefing-now" in args)


if __name__ == "__main__":
    main()
