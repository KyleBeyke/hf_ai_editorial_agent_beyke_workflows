import json
from editorial_agent.events import JsonlEventLogger


def test_event_logger_hash_chains(tmp_path):
    logger = JsonlEventLogger(tmp_path / "events.jsonl")
    first = logger.emit("start", {"a": 1})
    second = logger.emit("end", {"b": 2})
    assert second.prev_hash == first.event_hash
    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "start"
