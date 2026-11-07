"""Contract smoke tests for the minimal fake Agent RPC HTTP target."""
import importlib.util
import pathlib
import unittest
import uuid

path = pathlib.Path(__file__).parent / "mock-agent/mock_agent.py"
spec = importlib.util.spec_from_file_location("bridge_mock", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def command(method, params):
    return {"version": 0, "id": str(uuid.uuid4()), "method": method,
            "error": "", "params": params}

class MockTests(unittest.TestCase):
    def setUp(self):
        mod.SESSIONS.clear()
        mod.TURNS.clear()
        mod.COMMANDS.clear()

    def test_create_turn_and_idempotence(self):
        p = {"agent_id": "mock", "workspace_key": "agentic-bridge-cli",
             "command_id": str(uuid.uuid4())}
        msg = command("server:session.create", p)
        code, reply = mod.dispatch(msg)
        self.assertEqual(code, "")
        self.assertEqual(mod.dispatch(msg), (code, reply))
        sid = reply["session"]["id"]
        turn_p = {"agent_id": "mock", "workspace_key": p["workspace_key"],
                  "session_id": sid, "command_id": str(uuid.uuid4()),
                  "input": [{"type": "text", "text": "hello"}]}
        turn = command("server:turn.start", turn_p)
        code, out = mod.dispatch(turn)
        self.assertEqual(code, "")
        self.assertEqual(out["status"], "accepted")
        self.assertEqual(mod.TURNS[out["turn_id"]]["status"], "completed")
        self.assertEqual(mod.dispatch(turn), (code, out))
        changed = command("server:turn.start", dict(turn_p, input=[{"type": "text", "text": "changed"}]))
        self.assertEqual(mod.dispatch(changed)[0], "COMMAND_ID_CONFLICT")

    def test_workspace_and_session_fail_closed(self):
        p = {"agent_id": "mock", "workspace_key": "/etc",
             "command_id": str(uuid.uuid4())}
        self.assertEqual(mod.dispatch(command("server:session.create", p))[0], "UNKNOWN_WORKSPACE")
        p["workspace_key"] = "agentic-bridge-ui"
        p.update(session_id="unknown", input=[{"type": "text", "text": "hi"}])
        self.assertEqual(mod.dispatch(command("server:turn.start", p))[0], "SESSION_NOT_FOUND")

if __name__ == "__main__":
    unittest.main()
