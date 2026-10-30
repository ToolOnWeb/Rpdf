"""Synthetic HTTP/Phoenix WebSocket acceptance for a single installed release."""

from __future__ import annotations

import argparse
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx
from websockets.sync.client import connect


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.csrf = None
        self.live = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("name") == "csrf-token":
            self.csrf = attrs["content"]
        if "data-phx-main" in attrs:
            self.live = attrs


def verify(base, *, origin=None, expected_release=None, hold=False):
    base = base.rstrip("/")
    parsed = urlsplit(base)
    with httpx.Client(base_url=base, timeout=30, follow_redirects=True) as client:
        response = client.get("/")
        response.raise_for_status()
        doc = Document(response.text)
        assert doc.csrf and doc.live and "PDF Control" in response.text
        if expected_release:
            assert response.headers.get("x-pm-release") == expected_release
        origin = origin or (parsed.scheme + "://" + parsed.netloc)
        cookie = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
        ws = ("wss" if parsed.scheme == "https" else "ws") + "://" + parsed.netloc
        ws += "/live/websocket?" + urlencode({"vsn": "2.0.0", "_csrf_token": doc.csrf})
        with connect(
            ws, origin=origin, additional_headers={"Cookie": cookie}, open_timeout=15
        ) as socket:
            socket.send(
                json.dumps(
                    [
                        "1",
                        "1",
                        "lv:" + doc.live["id"],
                        "phx_join",
                        {
                            "url": base + "/",
                            "params": {"_csrf_token": doc.csrf, "_mounts": 0},
                            "session": doc.live["data-phx-session"],
                            "static": doc.live.get("data-phx-static", ""),
                        },
                    ]
                )
            )
            reply = json.loads(socket.recv(timeout=15))
            assert reply[2] == "lv:" + doc.live["id"] and reply[3] == "phx_reply"
            assert reply[4]["status"] == "ok", reply[4]
            socket.send(json.dumps([None, "2", "phoenix", "heartbeat", {}]))
            heartbeat = json.loads(socket.recv(timeout=15))
            assert heartbeat[3] == "phx_reply" and heartbeat[4]["status"] == "ok"
            if hold:
                print(json.dumps({"joined": True}), flush=True)
                for action in sys.stdin:
                    if action.strip() == "close":
                        break
                    if action.strip() != "check":
                        raise ValueError("Unexpected control action")
                    socket.send(json.dumps([None, "3", "phoenix", "heartbeat", {}]))
                    answer = json.loads(socket.recv(timeout=15))
                    assert answer[3] == "phx_reply" and answer[4]["status"] == "ok"
                    print(json.dumps({"alive": True}), flush=True)
        result = {
            "http": response.status_code,
            "websocket_join": True,
            "heartbeat": True,
            "observed_release": response.headers.get("x-pm-release"),
            "session_cookie_present": bool(cookie),
        }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument("--origin")
    parser.add_argument("--release")
    parser.add_argument("--output")
    parser.add_argument("--hold", action="store_true")
    args = parser.parse_args()
    result = verify(args.base, origin=args.origin, expected_release=args.release, hold=args.hold)
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
