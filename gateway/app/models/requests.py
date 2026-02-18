from pydantic import BaseModel
from typing import Any

class ModelRequest(BaseModel):
    provider: str
    model: str
    temperature: float
    max_tokens: int

class AICallRequest(BaseModel):
    prompt: str
    environment: str
    client_id: str
    feature_tag: str
    model_request: ModelRequest
    intent_manifest: str = "text-generation"
    user_ref: str = "system"
    rag_context: dict | list | None = None
    tool_permissions: list[str] = []
    network_access: bool = False
