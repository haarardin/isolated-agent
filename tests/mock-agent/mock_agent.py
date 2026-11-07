#!/usr/bin/env python3
"""Private, test-only Bridge RPC mock over HTTP. NOT a production agent.

Current agentic-bridge-cli has no production mock adapter: send test frames
from Codex's container with curl, then implement the CLI adapter separately.
"""
import json
import re
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

WORKSPACES = frozenset(("agentic-bridge-cli", "agentic-bridge-architecture",
                        "agentic-bridge-server", "agentic-bridge-ui"))
SESSIONS = {}
TURNS = {}
COMMANDS = {}
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def is_uuid(value):
    try:
        return isinstance(value, str) and bool(UUID_RE.fullmatch(value)) and str(uuid.UUID(value)) == value
    except ValueError:
        return False


def dispatch(frame):
    if not isinstance(frame, dict) or frame.get("version") != 0:
        return "INVALID_REQUEST", {"message": "Expected version 0"}
    method = frame.get("method")
    allowed = ("server:agent.list", "server:agent.capabilities",
               "server:session.create", "server:turn.start")
    if method not in allowed:
        return "UNSUPPORTED_CAPABILITY", {"message": "Method not implemented in mock"}
    p = frame.get("params")
    if not isinstance(p, dict) or frame.get("error") != "":
        return "INVALID_REQUEST", {"message": "Invalid RPC envelope"}
    if method == "server:agent.list":
        return "", {"agents": [{"agent_id": "mock", "kind": "mock",
                                "label": "Mock Agent", "state": "ready"}]}
    if p.get("agent_id") != "mock":
        return "UNKNOWN_AGENT", {"message": "Only mock agent exists"}
    if method == "server:agent.capabilities":
        return "", {"agent_id": "mock", "state": "ready",
                    "supported_methods": ["agent.list", "agent.capabilities",
                                          "session.create", "turn.start"],
                    "input_types": ["text"], "event_types": ["turn.completed"]}
    workspace = p.get("workspace_key")
    if workspace not in WORKSPACES:
        return "UNKNOWN_WORKSPACE", {"message": "Workspace not allowlisted"}
    cmd = p.get("command_id")
    if not is_uuid(cmd):
        return "INVALID_ARGUMENT", {"message": "Canonical command UUID required"}
    if cmd in COMMANDS:
        prev_method, prev_params, result = COMMANDS[cmd]
        if prev_method != method or prev_params != p:
            return "COMMAND_ID_CONFLICT", {"message": "command_id reused with different arguments"}
        return "", result
    if method == "server:session.create":
        sid = "mock-session-" + cmd
        SESSIONS[sid] = workspace
        result = {"session": {"id": sid, "agent_id": "mock",
                              "workspace_key": workspace}}
    else:
        sid = p.get("session_id")
        if SESSIONS.get(sid) != workspace:
            return "SESSION_NOT_FOUND", {"message": "Invalid session/workspace"}
        parts = p.get("input")
        if not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict):
            return "INVALID_ARGUMENT", {"message": "Expected exactly one text part"}
        part = parts[0]
        if part.get("type") != "text" or not isinstance(part.get("text"), str) or not (1 <= len(part["text"]) <= 4096):
            return "INVALID_ARGUMENT", {"message": "Invalid text input"}
        tid = "mock-turn-" + cmd
        output = "[mock] Completed in " + workspace + ": " + part["text"][:200]
        TURNS[tid] = {"turn_id": tid, "session_id": sid, "status": "completed",
                      "output": output,
                      "events": [{"type": "turn.started"},
                                 {"type": "turn.completed", "text": output}]}
        result = {"status": "accepted", "turn_id": tid}
    COMMANDS[cmd] = (method, p, result)
    return "", result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log untrusted prompts or secret-bearing bodies.

    def write_json(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            return self.write_json(200, {"ok": True, "service": "bridge-mock-agent"})
        if path.startswith("/v1/turns/"):
            turn = TURNS.get(path.removeprefix("/v1/turns/"))
            if turn:
                return self.write_json(200, turn)
        return self.write_json(404, {"error": "NOT_FOUND"})

    def do_POST(self):
        if urlsplit(self.path).path != "/rpc":
            return self.write_json(404, {"error": "NOT_FOUND"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= 65536:
            return self.write_json(413, {"error": "FRAME_TOO_LARGE"})
        try:
            frame = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            return self.write_json(400, {"error": "INVALID_JSON"})
        if not isinstance(frame, dict) or not is_uuid(frame.get("id")):
            return self.write_json(400, {"error": "INVALID_RPC_ID"})
        code, payload = dispatch(frame)
        method = frame.get("method")
        operation = method.removeprefix("server:") if isinstance(method, str) else "invalid"
        reply = {"version": 0, "id": frame["id"],
                 "method": "client:" + operation + ".result",
                 "error": code, "params": payload}
        self.write_json(200, reply)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
