#!/usr/bin/env python3
"""
One command, no arguments:

    python app.py

Opens the walkthrough in your browser. The two sample reviews work with zero
setup. To review your own contracts live, set ANTHROPIC_API_KEY first and
install the dependencies (pip install -r requirements.txt).
"""

import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "demo"))

PORT = int(os.environ.get("PORT", 8742))


def run_live_review(text: str) -> dict:
    try:
        import review as r
    except ImportError as e:
        return {"error": f"Missing dependency ({e.name}). Run: pip install -r requirements.txt"}
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"error": "ANTHROPIC_API_KEY is not set. Set it in this terminal and restart app.py."}
    try:
        playbook = r.load_playbook()
        precedents = r.load_precedents(playbook["contract_type"])
        raw = r.call_model(r.SYSTEM_PROMPT, r.build_user_prompt(text, playbook, precedents), r.DEFAULT_MODEL)
        result = r.parse_review(raw)
        r.verify_quotes(result, text)
        r.OUTPUTS_DIR.mkdir(exist_ok=True)
        (r.OUTPUTS_DIR / "live_review.review.json").write_text(json.dumps(result, indent=2))
        (r.OUTPUTS_DIR / "live_review.review.md").write_text(r.to_markdown(result, "pasted contract"))
        return result
    except Exception as e:  # surface the real reason; this is a spike, not a black box
        return {"error": f"Review failed: {type(e).__name__}: {e}"}


def record_precedent(payload: dict) -> dict:
    import datetime
    path = ROOT / "demo" / "precedents.jsonl"
    next_id = sum(1 for _ in open(path)) + 1 if path.exists() else 1
    entry = {
        "id": f"P-{next_id:03d}",
        "date": datetime.date.today().isoformat(),
        "contract_type": "mutual_nda",
        "playbook_ref": payload.get("playbook_ref", "uncovered"),
        "counterparty_position": payload.get("quote", "")[:200],
        "decision": "accepted_suggestion",
        "language": payload.get("language"),
        "notes": "Recorded from the walkthrough app.",
        "approved_by": "walkthrough",
    }
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return {"ok": True, "id": entry["id"]}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        if self.path in ("/", "/index.html", "/START_HERE.html"):
            self._send(200, (ROOT / "START_HERE.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/health":
            self._json({"live": True, "key": bool(os.environ.get("ANTHROPIC_API_KEY"))})
        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "Body was not valid JSON."}, 400)
        if self.path == "/api/review":
            self._json(run_live_review(payload.get("text", "")))
        elif self.path == "/api/record":
            self._json(record_precedent(payload))
        else:
            self._json({"error": "Not found"}, 404)

    def log_message(self, fmt, *args):  # keep the terminal calm
        pass


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    key = "set" if os.environ.get("ANTHROPIC_API_KEY") else "NOT set (samples still work; live reviews disabled)"
    print(f"Precedent walkthrough running at {url}")
    print(f"ANTHROPIC_API_KEY: {key}")
    print("Press Ctrl+C to stop.")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
