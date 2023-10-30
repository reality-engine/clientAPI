from fastapi import APIRouter, WebSocket

from .ai import call_eeg_to_text
from .models import Message
from .websockets import json_emitter

router = APIRouter()


@router.websocket("/text")
async def connect(ws: WebSocket):
    async for data in json_emitter(ws):
        msg = Message.model_validate(data)
        if msg.triggered:
            text = call_eeg_to_text(msg.values)
            await ws.send_json({"text": text})
        else:
            await ws.send_json({"ack": "received"})
