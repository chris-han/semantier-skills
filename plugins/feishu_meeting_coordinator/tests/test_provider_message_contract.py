from __future__ import annotations

from types import SimpleNamespace

from feishu_meeting_coordinator.scripts import feishu_bot_api as api


class _Resp:
    def __init__(self, data):
        self.data = data
        self.code = 0
        self.msg = ""

    def success(self):
        return True


class _MessageApi:
    def __init__(self):
        self.created = []
        self.get_requests = []

    def create(self, req):
        self.created.append(req)
        target = req.request_body.receive_id
        return _Resp(SimpleNamespace(message_id=f"om_{target}", deleted=False))

    def get(self, req):
        self.get_requests.append(req)
        message_id = req.paths["message_id"]
        item = SimpleNamespace(
            message_id=message_id,
            msg_type="text",
            create_time=1,
            update_time=2,
            deleted=False,
            chat_id="oc_chat",
            body=SimpleNamespace(content='{"text":"hello"}'),
        )
        return _Resp(SimpleNamespace(items=[item]))


class _Client:
    def __init__(self):
        self.im = SimpleNamespace(
            v1=SimpleNamespace(
                message=_MessageApi(),
            )
        )


def test_send_attendee_message_returns_provider_id_and_stable_uuid(monkeypatch):
    client = _Client()
    monkeypatch.setattr(api, "_get_client", lambda: client)

    first = api.send_attendee_message(
        attendee_open_ids=["ou_a"],
        message="hello",
        idempotency_key="effect-123",
    )
    second = api.send_attendee_message(
        attendee_open_ids=["ou_a"],
        message="hello",
        idempotency_key="effect-123",
    )

    assert first["message_id"] == "om_ou_a"
    assert first["message_ids"] == {"ou_a": "om_ou_a"}
    assert second["message_id"] == "om_ou_a"
    assert len(client.im.v1.message.created) == 2
    first_uuid = client.im.v1.message.created[0].request_body.uuid
    second_uuid = client.im.v1.message.created[1].request_body.uuid
    assert first_uuid
    assert first_uuid == second_uuid
    assert len(first_uuid) <= 50


def test_send_attendee_message_derives_distinct_uuid_per_target(monkeypatch):
    client = _Client()
    monkeypatch.setattr(api, "_get_client", lambda: client)

    result = api.send_attendee_message(
        attendee_open_ids=["ou_a", "ou_b"],
        message="hello",
        idempotency_key="effect-123",
    )

    assert result["delivered"] == ["ou_a", "ou_b"]
    assert result["message_ids"] == {
        "ou_a": "om_ou_a",
        "ou_b": "om_ou_b",
    }
    uuids = [req.request_body.uuid for req in client.im.v1.message.created]
    assert len(set(uuids)) == 2


def test_get_message_returns_normalized_provider_record(monkeypatch):
    client = _Client()
    monkeypatch.setattr(api, "_get_client", lambda: client)

    result = api.get_message(message_id="om_123")

    assert result["found"] is True
    assert result["message_id"] == "om_123"
    assert result["message"]["message_id"] == "om_123"
    assert result["message"]["deleted"] is False
    assert client.im.v1.message.get_requests[0].paths["message_id"] == "om_123"
