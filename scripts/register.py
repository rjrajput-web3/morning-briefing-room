#!/usr/bin/env python3
"""One-time setup: register the briefing-room agent and create its room.

Reads SWITCH_API and AGENT_REGISTRATION_TOKEN from the environment.
Saves agent id, api key and room id to agent-state.json (gitignored —
never commit it).
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("SWITCH_API", "http://localhost:8000")
REG_TOKEN = os.environ.get("AGENT_REGISTRATION_TOKEN")
if not REG_TOKEN:
    sys.exit("Set AGENT_REGISTRATION_TOKEN first.")

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "agent-state.json")


def call(method, path, bearer, body=None):
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {bearer}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:500]}


def main():
    s, b = call("GET", "/health", "")
    print("health:", s, b)
    if s != 200:
        sys.exit("Switch API not reachable at " + API)

    profile = {
        "connection_model": "always_on",
        "message_exchange": True,
        "pre_invocation_mediation": [],
        "post_invocation_mediation": [],
        "event_reporting": [],
    }
    s, b = call("POST", "/agents", REG_TOKEN, {
        "name": "briefing-room",
        "description": "Morning Briefing Room agent - Flip the Switch hackathon",
        "connector_type": "custom",
        "integration_profile": profile,
        "overwrite": True,
    })
    print("register:", s)
    agent_id, api_key = b.get("id"), b.get("api_key")
    if not api_key:
        sys.exit("FATAL: no api_key returned")

    s, room = call("POST", f"/agents/{agent_id}/ops/create_room", api_key, {
        "name": "morning-briefing-room",
        "description": "Morning Briefing Room",
        "agent_names": ["briefing-room"],
    })
    print("create_room:", s)
    room_id = (room.get("result") or {}).get("id")
    if not room_id:
        sys.exit("FATAL: no room_id")

    s, msg = call("POST", f"/agents/{agent_id}/message", api_key, {
        "room_id": room_id,
        "content": "Hey! Ping @briefing-room and I'll jump in.",
    })
    print("welcome message:", s)

    state = {"agent_id": agent_id, "api_key": api_key, "room_id": room_id}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    os.chmod(STATE_FILE, 0o600)
    print(f"OK - state saved to {STATE_FILE} (gitignored, keep it secret)")


if __name__ == "__main__":
    main()
