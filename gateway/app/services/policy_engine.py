"""
Policy Engine for CDIL Gateway.

Evaluates governance policies pre-execution.
This is a stub implementation shaped correctly for production.
"""

from typing import Dict, Any
from datetime import datetime, timezone
import time

from gateway.app.services.hashing import sha256_hex

# Stub policy version for dev
POLICY_VERSION = "v1.0.0-dev"
POLICY_CHANGE_REF = "PCR-DEV-0001"

# Default environment
DEFAULT_ENVIRONMENT = "prod"

# Allowed models (allowlist)
ALLOWED_MODELS = ["gpt-4", "gpt-3.5-turbo", "claude-3-sonnet"]

# Allowed tools (allowlist)
ALLOWED_TOOLS = ["web_search", "calculator", "code_interpreter"]


def evaluate_request(request: Dict[str, Any], environment: str) -> Dict[str, Any]:
    """
    Evaluate a request against governance policy.

    This is a stub implementation that enforces:
    - Model allowlist
    - Temperature constraints by feature_tag
    - Network access rules
    - Tool permissions allowlist

    Args:
        request: Request dictionary with:
            - model: Model identifier
            - temperature: Temperature parameter
            - feature_tag: Feature tag (e.g., "billing")
            - environment: Environment name
            - intent_manifest: Intent type
            - network_access: Whether network access is requested (default: False)
            - tool_permissions: List of requested tool permissions (default: [])
        environment: Environment name (prod, staging, dev)

    Returns:
        Policy receipt dictionary with:
            - policy_version_hash: SHA-256 hash of policy version
            - policy_change_ref: Policy change reference ID
            - rules_applied: List of rules that were applied
            - decision: "approved" or "denied"
            - decision_timestamp_utc: ISO 8601 timestamp
            - evaluation_latency_ms: Evaluation time in milliseconds
            - denial_reasons: List of denial reasons (if denied)
    """
    start_time = time.time()

    rules_applied = []
    decision = "approved"
    denial_reasons = []

    # Rule 1: Model allowlist
    rules_applied.append("model_allowlist")
    if request.get("model") not in ALLOWED_MODELS:
        decision = "denied"
        denial_reasons.append(f"Model '{request.get('model')}' not in allowlist")

    # Rule 2: Temperature constraint for billing feature
    feature_tag = request.get("feature_tag", "")
    temperature = request.get("temperature", 0.7)

    if feature_tag == "billing":
        rules_applied.append("billing_temp_zero")
        if temperature != 0.0:
            decision = "denied"
            denial_reasons.append(
                f"Billing feature requires temperature=0.0, got {temperature}"
            )

    # Rule 3: Network access must be False in prod for billing
    network_access = request.get("network_access", False)
    if environment == "prod" and feature_tag == "billing":
        rules_applied.append("billing_network_denied")
        if network_access:
            decision = "denied"
            denial_reasons.append(
                "Billing feature in prod environment prohibits network access"
            )

    # Rule 4: Tool permissions allowlist
    tool_permissions = request.get("tool_permissions", [])
    if tool_permissions:
        rules_applied.append("tool_allowlist")
        forbidden_tools = [
            tool for tool in tool_permissions if tool not in ALLOWED_TOOLS
        ]
        if forbidden_tools:
            decision = "denied"
            denial_reasons.append(
                f"Tools not in allowlist: {', '.join(forbidden_tools)}"
            )

    # Compute policy version hash (deterministic)
    policy_version_hash = sha256_hex(POLICY_VERSION.encode("utf-8"))

    # Timestamp
    decision_timestamp_utc = (
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    # Latency
    end_time = time.time()
    evaluation_latency_ms = int((end_time - start_time) * 1000)

    return {
        "policy_version_hash": policy_version_hash,
        "policy_change_ref": POLICY_CHANGE_REF,
        "rules_applied": rules_applied,
        "decision": decision,
        "decision_timestamp_utc": decision_timestamp_utc,
        "evaluation_latency_ms": evaluation_latency_ms,
        "denial_reasons": denial_reasons if denial_reasons else None,
    }
