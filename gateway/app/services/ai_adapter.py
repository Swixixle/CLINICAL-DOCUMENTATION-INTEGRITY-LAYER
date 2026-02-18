"""
AI Adapter for CDIL Gateway.

Executes AI model calls (stub implementation).
"""

from typing import Dict, Any
import time

from gateway.app.services.hashing import sha256_hex


def execute(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute an AI model call.
    
    This is a stub implementation that returns a deterministic response.
    In production, this would call the actual AI provider.
    
    Args:
        request: Request dictionary with:
            - prompt: Prompt text
            - model: Model identifier
            - temperature: Temperature parameter
            
    Returns:
        Execution dictionary with:
            - outcome: "approved" (always for executed requests)
            - output_text: Response text
            - output_hash: SHA-256 hash of output
            - token_usage: Token usage stats (optional)
            - latency_ms: Execution latency in milliseconds
            - cost_estimate_usd: Estimated cost (optional)
    """
    start_time = time.time()
    
    # Stub response
    output_text = f"This is a stubbed response to: {request.get('prompt', '')[:50]}..."
    output_hash = sha256_hex(output_text.encode('utf-8'))
    
    # Simulate some latency
    time.sleep(0.005)  # 5ms
    
    end_time = time.time()
    latency_ms = int((end_time - start_time) * 1000)
    
    return {
        "outcome": "approved",
        "output_text": output_text,
        "output_hash": output_hash,
        "token_usage": {
            "prompt_tokens": 10,
            "completion_tokens": 15,
            "total_tokens": 25
        },
        "latency_ms": latency_ms,
        "cost_estimate_usd": 0.0001
    }
