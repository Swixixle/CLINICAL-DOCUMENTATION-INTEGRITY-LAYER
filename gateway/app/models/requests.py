from pydantic import BaseModel
from typing import Any

class ModelRequest(BaseModel):
    provider: str
    model: str
    temperature: float
    max_tokens: int

class AICallRequest(BaseModel):
    intent_manifest: str
    feature_tag: str
    user_ref: str
    model_request: ModelRequest
    prompt: str
    environment: str
    client_id: str
    rag_context: dict | list | None = None
    tool_permissions: list[str] = []
    network_access: bool = False
