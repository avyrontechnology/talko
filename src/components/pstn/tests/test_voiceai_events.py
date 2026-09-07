import copy
import json

from src.components.pstn.voiceai_events import forward_to_voiceai, parse_from_voiceai


def _tata_start():
    return {
        "event": "start",
        "streamSid": "MZ123",
        "start": {
            "callSid": "CA123",
            "streamSid": "MZ123",
            "from": "919812345678",
            "to": "918045678901",
            "direction": "outbound",
        },
    }


class TestForwardToVoiceai:
    def test_start_forwarded_verbatim(self):
        event = _tata_start()
        out = json.loads(forward_to_voiceai(event))
        assert out["start"]["callSid"] == "CA123"
        assert out["start"]["streamSid"] == "MZ123"

    def test_media_gets_timestamp_from_chunk(self):
        event = {
            "event": "media",
            "streamSid": "MZ123",
            "media": {"payload": "aGk=", "chunk": 50},
        }
        out = json.loads(forward_to_voiceai(event))
        assert out["media"]["payload"] == "aGk="
        assert out["media"]["chunk"] == 50  # tata field preserved
        assert out["media"]["timestamp"] == 1000  # 50 chunks * 20ms

    def test_media_keeps_existing_timestamp(self):
        event = {
            "event": "media",
            "media": {"payload": "aGk=", "chunk": 3, "timestamp": 999},
        }
        out = json.loads(forward_to_voiceai(event))
        assert out["media"]["timestamp"] == 999

    def test_media_without_chunk_uses_hint(self):
        event = {"event": "media", "media": {"payload": "aGk="}}
        out = json.loads(forward_to_voiceai(event, chunk_hint=420))
        assert out["media"]["timestamp"] == 420

    def test_does_not_mutate_input(self):
        event = {"event": "media", "media": {"payload": "aGk=", "chunk": 1}}
        forward_to_voiceai(event)
        assert "timestamp" not in event["media"]

    def test_mark_and_stop_forwarded(self):
        mark = {"event": "mark", "streamSid": "MZ1", "mark": {"name": "m1"}}
        assert json.loads(forward_to_voiceai(mark))["mark"]["name"] == "m1"
        stop = {"event": "stop", "streamSid": "MZ1", "stop": {"reason": "hangup"}}
        assert json.loads(forward_to_voiceai(stop))["event"] == "stop"

    def test_connected_and_clear_dropped(self):
        assert forward_to_voiceai({"event": "connected"}) is None
        assert forward_to_voiceai({"event": "clear", "streamSid": "MZ1"}) is None
        assert forward_to_voiceai({"event": "weird"}) is None


class TestParseFromVoiceai:
    def test_media(self):
        import base64

        raw = json.dumps(
            {"event": "media", "streamSid": "MZ1", "media": {"payload": base64.b64encode(b"\x01\x02").decode()}}
        )
        kind, payload = parse_from_voiceai(raw)
        assert kind == "media" and payload == b"\x01\x02"

    def test_media_bad_payload_ignored(self):
        raw = json.dumps({"event": "media", "media": {}})
        assert parse_from_voiceai(raw) == (None, None)

    def test_mark_name_preserved(self):
        raw = json.dumps({"event": "mark", "streamSid": "MZ1", "mark": {"name": "uuid-1"}})
        assert parse_from_voiceai(raw) == ("mark", "uuid-1")

    def test_mark_without_name_ignored(self):
        assert parse_from_voiceai('{"event": "mark"}') == (None, None)

    def test_clear(self):
        assert parse_from_voiceai('{"event": "clear", "streamSid": "MZ1"}') == ("clear", None)

    def test_garbage_ignored(self):
        assert parse_from_voiceai("not json") == (None, None)
        assert parse_from_voiceai('{"event": "connected"}') == (None, None)

    def test_input_event_copy_untouched(self):
        event = _tata_start()
        snapshot = copy.deepcopy(event)
        forward_to_voiceai(event)
        assert event == snapshot
