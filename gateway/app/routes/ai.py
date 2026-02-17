"""
AI call endpoint for processing AI requests.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid

from gateway.app.services.policy_engine import evaluate_request
from gateway.app.services.ai_adapter import execute
from gateway.app.services.packet_builder import build_accountability_packet
from gateway.app.services.storage import store_transaction
from gateway.app.services.hashing import sha256_hex, hash_c14n

router = APIRouter(prefix="/v1/ai", tags=["ai"])


class AICallRequest(BaseModel):
    """Request body for /v1/ai/call endpoint."""
    prompt: str = Field(..., description="The prompt text to send to the AI model")
    environment: str = Field(..., description="Environment: production, staging, or dev")
    client_id: str = Field(..., description="Client identifier")
    feature_tag: str = Field(..., description="Feature tag (e.g., billing, customer-support)")
    user_ref: str = Field(default="system", description="User reference")
    model: str = Field(..., description="Model identifier")
    temperature: float = Field(default=0.7, description="Model temperature parameter")
    rag_context: Optional[Dict[str, Any]] = Field(default=None, description="Optional RAG context")
    intent_manifest: str = Field(default="text-generation", description="Intent type")


class AICallResponse(BaseModel):
    """Response from /v1/ai/call endpoint."""
    transaction_id: str
    status: str  # "completed" or "denied"
    output: Optional[str] = None
    accountability: Dict[str, Any]


@router.post("/call", response_model=AICallResponse)
async def ai_call(request: AICallRequest) -> AICallResponse:
    """
    Process an AI call with full governance and accountability.
    
    Flow:
    1. Generate transaction_id and timestamp
    2. Compute content hashes
    3. Evaluate policy (pre-execution)
    4. Execute AI call if approved
    5. Build accountability packet
    6. Persist to database
    7. Return response
    """
    # Step 1: Generate transaction_id and timestamp
    transaction_id = str(uuid.uuid4())
    gateway_timestamp_utc = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    # Step 2: Compute content hashes
    prompt_hash = sha256_hex(request.prompt.encode('utf-8'))
    
    rag_hash = None
    if request.rag_context:
        rag_hash = hash_c14n(request.rag_context)
    
    # Step 3: Evaluate policy (pre-execution)
    policy_request = {
        "model": request.model,
        "temperature": request.temperature,
        "feature_tag": request.feature_tag,
        "environment": request.environment,
        "intent_manifest": request.intent_manifest
    }
    
    policy_receipt = evaluate_request(policy_request, request.environment)
    
    # Step 4: Execute AI call or create denial stub
    if policy_receipt["decision"] == "approved":
        execution = execute({
            "prompt": request.prompt,
            "model": request.model,
            "temperature": request.temperature
        })
    else:
        # Denied execution stub
        denial_reasons = policy_receipt.get("denial_reasons") or []
        denial_message = "; ".join(denial_reasons) if denial_reasons else "Policy denied"
        execution = {
            "outcome": "denied",
            "output_hash": None,
            "token_usage": None,
            "latency_ms": 0,
            "denial_reason": denial_message
        }
    
    # Step 5: Build accountability packet
    packet = build_accountability_packet(
        transaction_id=transaction_id,
        gateway_timestamp_utc=gateway_timestamp_utc,
        environment=request.environment,
        client_id=request.client_id,
        intent_manifest=request.intent_manifest,
        feature_tag=request.feature_tag,
        user_ref=request.user_ref,
        prompt_hash=prompt_hash,
        rag_hash=rag_hash,
        multimodal_hash=None,
        policy_version_hash=policy_receipt["policy_version_hash"],
        policy_change_ref=policy_receipt["policy_change_ref"],
        rules_applied=policy_receipt["rules_applied"],
        model_fingerprint=request.model,
        param_snapshot={"temperature": request.temperature},
        execution=execution
    )
    
    # Step 6: Persist to database
    store_transaction(packet)
    
    # Step 7: Return response
    status = "completed" if execution["outcome"] == "approved" else "denied"
    output_text = execution.get("output_text") if execution["outcome"] == "approved" else None
    
    return AICallResponse(
        transaction_id=transaction_id,
        status=status,
        output=output_text,
        accountability={
            "policy_version_hash": policy_receipt["policy_version_hash"],
            "policy_change_ref": policy_receipt["policy_change_ref"],
            "final_hash": packet["halo_chain"]["final_hash"],
            "signed": True
        }
    )
