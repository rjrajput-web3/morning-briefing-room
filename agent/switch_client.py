"""Switch wire-protocol client: SSE down, HTTP up, 2s heartbeat.

Implements the connection lifecycle from the official agent-protocol doc:
open the event stream (declaring rooms on the URL), beat every 2 seconds,
reopen on 404/409. Thread-safe cursor handling.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import config


class SwitchError(Exception):
    pass


class SwitchClient:
    def __init__(self, api, agent_id, api_key):
        self.api = api.rstrip("/")
        self.agent_id = agent_id
        self.api_key = api_key

    def _req(self, method, path, body=None, timeout=30):
        req = urllib.request.Request(
            self.api + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            return e.code, {"error": e.read().decode()[:500]}

    # ---- simple HTTP calls (no connection needed) ----

    def post_message(self, room_id, content):
        s, b = self._req(
            "POST",
            f"/agents/{self.agent_id}/message",
            {"room_id": room_id, "content": content},
        )
        if s != 200:
            raise SwitchError(f"post_message -> {s}: {b}")
        return b

    def read_context(self, room_id, limit=50):
        s, b = self._req(
            "POST",
            f"/agents/{self.agent_id}/ops/read_context",
            {"room_id": room_id, "limit": limit},
        )
        if s != 200:
            raise SwitchError(f"read_context -> {s}: {b}")
        return b

    def list_participants(self, room_id):
        s, b = self._req(
            "POST",
            f"/agents/{self.agent_id}/ops/list_participants",
            {"room_id": room_id},
        )
        if s != 200:
            raise SwitchError(f"list_participants -> {s}: {b}")
        return b

    # ---- heartbeat ----

    def beat(self, connection_id, cursor):
        return self._req(
            "POST",
            f"/agents/{self.agent_id}/connection/beat",
            {"connection_id": connection_id, "cursor": cursor},
        )


class EventStream:
    """One SSE connection: reader thread -> event queue, heartbeat thread.

    The connection id is generated once and reused across reconnects (the
    connection outlives its socket). A reopen with the same id is a
    takeover — only one EventStream may run per id.
    """

    def __init__(self, client, room_id, on_event):
        self.client = client
        self.room_id = room_id
        self.on_event = on_event
        self.connection_id = str(uuid.uuid4())
        self.cursor = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads = []

    def _set_cursor(self, seq):
        with self._lock:
            if seq > self.cursor:
                self.cursor = seq

    def _get_cursor(self):
        with self._lock:
            return self.cursor

    def _heartbeat_loop(self, interval=2.0):
        while not self._stop.wait(interval):
            s, _ = self.client.beat(self.connection_id, self._get_cursor())
            if s in (404, 409):
                # Connection dead — the reader loop will reopen it.
                print(f"[stream] beat -> {s}, will reopen")

    def _parse_sse(self, resp):
        """Yield (event_name, data_dict) frames from a raw SSE response."""
        buf_name, buf_data, buf_id = None, [], None
        while not self._stop.is_set():
            line = resp.readline()
            if not line:
                break  # socket closed
            line = line.decode("utf-8", "replace").rstrip("\n")
            if line == "":
                if buf_name or buf_data:
                    try:
                        data = json.loads("\n".join(buf_data)) if buf_data else {}
                    except json.JSONDecodeError:
                        data = {}
                    if buf_id is not None:
                        try:
                            self._set_cursor(int(buf_id))
                        except ValueError:
                            pass
                    yield buf_name, data
                buf_name, buf_data, buf_id = None, [], None
            elif line.startswith(":"):
                continue  # keepalive comment
            elif line.startswith("event:"):
                buf_name = line[6:].strip()
            elif line.startswith("data:"):
                buf_data.append(line[5:].strip())
            elif line.startswith("id:"):
                buf_id = line[3:].strip()

    def _open_stream(self):
        qs = urllib.parse.urlencode(
            {
                "connection_id": self.connection_id,
                "scope": "single",
                "rooms": self.room_id,
                "filter": "all",
            }
        )
        req = urllib.request.Request(
            f"{self.client.api}/agents/{self.client.agent_id}/events?{qs}",
            headers={"Authorization": f"Bearer {self.client.api_key}",
                     "Accept": "text/event-stream"},
        )
        return urllib.request.urlopen(req, timeout=90)

    def _reader_loop(self):
        backoff = 2
        while not self._stop.is_set():
            try:
                resp = self._open_stream()
                print("[stream] opened")
                backoff = 2
                for name, data in self._parse_sse(resp):
                    if name == "evicted":
                        print(f"[stream] evicted: {data}")
                        # fall through to reopen (takeover by sibling)
                        break
                    if name in ("message", "command", "room_join"):
                        try:
                            self.on_event(name, data)
                        except Exception as e:
                            print(f"[stream] handler error: {e}")
                resp.close()
            except Exception as e:
                print(f"[stream] {type(e).__name__}: {e}")
            if self._stop.is_set():
                break
            print(f"[stream] reopening in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)

    def start(self):
        hb = threading.Thread(target=self._heartbeat_loop, daemon=True)
        rd = threading.Thread(target=self._reader_loop, daemon=True)
        hb.start()
        rd.start()
        self._threads = [hb, rd]

    def stop(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)
