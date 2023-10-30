from reapi.models import EEGValues, Message


def test_websocket(client):
    with client.websocket_connect("/connect/text") as ws:
        data = Message(triggered=False, values=EEGValues(Cx=1.0, Drm=2.0))
        ws.send_json(data.model_dump())
        data = ws.receive_json()
        assert data == {"ack": "received"}


def test_text(client):
    with client.websocket_connect("/connect/text") as ws:
        data = Message(triggered=True, values=EEGValues(Cx=1.0, Drm=2.0))
        ws.send_json(data.model_dump())
        data = ws.receive_json()
        assert data == {"text": ["Some", "ai", "generated", "data"]}
