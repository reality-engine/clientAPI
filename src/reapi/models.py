from pydantic import BaseModel


class EEGValues(BaseModel):
    Cx: float
    Drm: float


class Message(BaseModel):
    triggered: bool = False
    values: EEGValues
