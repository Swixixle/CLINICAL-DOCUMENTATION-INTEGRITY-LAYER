"""
Request models for AI calls.
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional, Dict, Any, List, Union


class ModelRequest(BaseModel):
    """Model configuration for AI requests."""
    provider: str = Field(default="openai", description="AI provider (e.g., 'openai', 'anthropic')")
    model: str = Field(..., description="Model identifier (e.g., 'gpt-4')")
    temperature: float = Field(..., description="Model temperature parameter")
    max_tokens: int = Field(default=2048, description="Maximum tokens to generate")


class AICallRequest(BaseModel):
    """Request body for /v1/ai/call endpoint."""
    # Core fields
    environment: str = Field(..., description="Environment: prod, staging, or dev")
    client_id: str = Field(..., description="Client identifier")
    feature_tag: str = Field(..., description="Feature tag (e.g., billing, customer-support)")
    user_ref: str = Field(default="system", description="User reference")
    intent_manifest: str = Field(default="text-generation", description="Intent type")
    
    # Prompt
    prompt: Union[str, List[Any]] = Field(..., description="The prompt text or messages to send to the AI model")
    
    # Optional context
    rag_context: Optional[Union[Dict[str, Any], List[Any]]] = Field(default=None, description="Optional RAG context")
    
    # New governance fields
    tool_permissions: List[str] = Field(default_factory=list, description="List of allowed tool names")
    network_access: bool = Field(default=False, description="Whether network access is allowed")
    
    # Support both new model_request and legacy model/temperature
    model_request: Optional[ModelRequest] = Field(default=None, description="Model configuration (new format)")
    model: Optional[str] = Field(default=None, description="Model identifier (legacy)")
    temperature: Optional[float] = Field(default=None, description="Model temperature (legacy)")
    
    @model_validator(mode='after')
    def validate_model_fields(self):
        """Ensure either model_request or legacy model/temperature is provided."""
        if self.model_request is None and self.model is None:
            raise ValueError("Either model_request or model field must be provided")
        return self
