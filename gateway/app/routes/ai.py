"""
AI call endpoint for processing AI requests.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid

from gateway.app.models import AICallRequest, ModelRequest
from gateway.app.services.policy_engine import evaluate_request
from gateway.app.services.ai_adapter import execute
from gateway.app.services.packet_builder import build_accountability_packet
from gateway.app.services.storage import store_transaction
from gateway.app.services.hashing import sha256_hex, hash_c14n

router = APIRouter(prefix="/v1/ai", tags=["ai"])


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
    
    # Handle both new model_request and legacy model/temperature fields
    if hasattr(request, 'model') and request.model:
        # Legacy format
        model = request.model
        temperature = request.temperature if request.temperature is not None else 0.7
    else:
        # New format
        model = request.model_request.model
        temperature = request.model_request.temperature
    
    # Step 2: Compute content hashes
    prompt_text = request.prompt if isinstance(request.prompt, str) else str(request.prompt)
    prompt_hash = sha256_hex(prompt_text.encode('utf-8'))
    
    rag_hash = None
    if request.rag_context:
        rag_hash = hash_c14n(request.rag_context)
    
    # Step 3: Evaluate policy (pre-execution)
    policy_request = {
        "model": model,
        "temperature": temperature,
        "feature_tag": request.feature_tag,
        "environment": request.environment,
        "intent_manifest": request.intent_manifest,
        "network_access": request.network_access,
        "tool_permissions": request.tool_permissions
    }
    
    policy_receipt = evaluate_request(policy_request, request.environment)
    
    # Step 4: Execute AI call or create denial stub
    if policy_receipt["decision"] == "approved":
        execution = execute({
            "prompt": prompt_text,
            "model": model,
            "temperature": temperature
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
        policy_decision=policy_receipt["decision"],
        model_fingerprint=model,
        param_snapshot={"temperature": temperature},
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
