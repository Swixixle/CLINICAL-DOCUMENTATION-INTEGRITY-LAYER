# Accountability Packet Refactoring

## Overview

This refactoring aligns the ELI Sentinel packet structure with the canonical Accountability Packet specification. The changes ensure protocol hardening for legal defensibility and eliminate ambiguity.

## Changes Made

### 1. Eliminated `packet_inputs` Wrapper ✅

**Before:**
```json
{
  "halo": {...},
  "signature": {...},
  "packet_inputs": {
    "transaction_id": "...",
    "intent_manifest": "...",
    ...
  }
}
```

**After:**
```json
{
  "transaction_id": "...",
  "client_id": "...",
  "environment": "...",
  "gateway_timestamp_utc": "...",
  
  "intent_manifest": "...",
  "feature_tag": "...",
  "user_ref": "...",
  
  "model_fingerprint": "...",
  "param_snapshot": {...},
  
  "prompt_hash": "...",
  "rag_hash": null,
  "multimodal_hash": null,
  
  "policy_receipt": {...},
  "execution": {...},
  "halo_chain": {...},
  "verification": {...},
  "protocol_metadata": {...}
}
```

All fields are now at the top level with proper grouping through `policy_receipt` and `execution` objects.

### 2. Refactored HALO Builder with Explicit Parameters ✅

**Before:**
```python
def build_halo_chain(packet_inputs: Dict[str, Any]) -> Dict[str, Any]:
    # Used loosely structured dict
    transaction_id = packet_inputs["transaction_id"]
    ...
```

**After:**
```python
def build_halo_chain(
    transaction_id: str,
    gateway_timestamp_utc: str,
    environment: str,
    client_id: str,
    intent_manifest: str,
    feature_tag: str,
    user_ref: str,
    prompt_hash: str,
    rag_hash: Optional[str],
    multimodal_hash: Optional[str],
    policy_version_hash: str,
    policy_change_ref: str,
    rules_applied: List[str],
    model_fingerprint: str,
    param_snapshot: Dict[str, Any],
    execution: Dict[str, Any]
) -> Dict[str, Any]:
    # Uses explicit typed parameters
    ...
```

Benefits:
- Type safety
- No ambiguity about required fields
- IDE autocomplete support
- Prevents silent drift

### 3. Locked Canonical Message Contract ✅

The signed message is now strictly limited to **exactly 4 fields**:

```python
canonical_message = {
    "transaction_id": "...",
    "gateway_timestamp_utc": "...",
    "final_hash": "...",
    "policy_version_hash": "..."
}
```

The `sign_message()` function now validates that the message contains exactly these fields and raises `ValueError` if additional or missing fields are detected.

**Why this matters:**
- Court systems punish ambiguity
- Future developers cannot accidentally add fields that break verification
- Signature verification is deterministic and predictable

### 4. Added Protocol Version Pins ✅

Added three constants to lock protocol versions:

```python
HALO_VERSION = "v1"
C14N_VERSION = "json_c14n_v1"
SIGNING_ALG = "ECDSA_SHA_256"
```

These are stored in every packet under `protocol_metadata`:

```json
{
  "protocol_metadata": {
    "halo_version": "v1",
    "c14n_version": "json_c14n_v1",
    "signing_alg": "ECDSA_SHA_256"
  }
}
```

**Why this matters:**
- Future upgrades can change algorithms
- Old packets declare which version they used
- Verifiers can handle multiple versions gracefully
- Protocol evolution is explicit, not implicit

### 5. Created Packet Builder ✅

New module: `gateway/app/services/packet_builder.py`

```python
def build_accountability_packet(
    transaction_id: str,
    gateway_timestamp_utc: str,
    environment: str,
    client_id: str,
    intent_manifest: str,
    feature_tag: str,
    user_ref: str,
    prompt_hash: str,
    rag_hash: Optional[str],
    multimodal_hash: Optional[str],
    policy_version_hash: str,
    policy_change_ref: str,
    rules_applied: List[str],
    model_fingerprint: str,
    param_snapshot: Dict[str, Any],
    execution: Dict[str, Any]
) -> Dict[str, Any]:
```

This function:
- Takes explicit structured inputs
- Builds the HALO chain
- Creates the canonical message
- Signs the message
- Assembles the complete packet
- Returns a protocol-correct, flat structure

### 6. Added Cross-Tool Determinism Test ✅

New test: `test_cross_tool_determinism()` in `test_packet_builder.py`

This test verifies:
1. ✅ Packet can be serialized to JSON
2. ✅ JSON can be deserialized
3. ✅ HALO can be recomputed from deserialized data
4. ✅ Signature can be verified
5. ✅ `final_hash` remains identical throughout

**Why this matters:**
- Catches hidden nondeterminism
- Ensures packets are portable
- Verifies offline verification works
- Guarantees cryptographic integrity across serialization boundaries

## Test Results

All 27 tests passing:

```
gateway/tests/test_c14n_vectors.py ............... 8 passed
gateway/tests/test_halo_vectors.py ............... 8 passed
gateway/tests/test_packet_builder.py ............. 5 passed
gateway/tests/test_sign_verify.py ................ 6 passed
```

Key new tests:
- `test_build_accountability_packet()` - Verifies packet structure
- `test_packet_no_wrapper()` - Confirms no packet_inputs wrapper
- `test_cross_tool_determinism()` - Guarantees serialize→deserialize→recompute integrity
- `test_protocol_version_pins()` - Validates protocol metadata
- `test_canonical_message_contract_enforced()` - Ensures 4-field signing contract

## Migration Notes

### For Future API Development

When building routes, use the packet builder:

```python
from gateway.app.services.packet_builder import build_accountability_packet

# In your route handler
packet = build_accountability_packet(
    transaction_id=generate_transaction_id(),
    gateway_timestamp_utc=get_utc_timestamp(),
    environment=config.environment,
    client_id=request.client_id,
    intent_manifest=request.intent_manifest,
    feature_tag=request.feature_tag,
    user_ref=request.user_ref,
    prompt_hash=hash_content(request.prompt),
    rag_hash=hash_content(request.rag) if request.rag else None,
    multimodal_hash=None,
    policy_version_hash=policy.version_hash,
    policy_change_ref=policy.change_ref,
    rules_applied=policy_engine.get_applied_rules(),
    model_fingerprint=request.model,
    param_snapshot=request.parameters,
    execution={
        "outcome": "approved",
        "output_hash": hash_content(response.output),
        "token_usage": response.usage,
        "latency_ms": response.latency_ms,
        "denial_reason": None
    }
)

# Store packet
db.store_packet(packet)

# Return receipt
return {"transaction_id": packet["transaction_id"], "final_hash": packet["halo_chain"]["final_hash"]}
```

### For Test Vectors

When creating test vectors, ensure they follow the new flat structure with no `packet_inputs` wrapper.

## What This Achieves

✅ **Deterministic canonicalization**
✅ **Deterministic HALO**
✅ **Deterministic signing**
✅ **Offline verification**
✅ **Schema-locked packet**
✅ **Version-pinned primitives**

This is now a **real trust engine** ready for:
- Legal proceedings
- Regulatory audits
- SOX/SOC2/ISO27001 compliance
- Insurance underwriting
- Litigation discovery

## Next Steps

Ready for:
1. FastAPI route implementation (`/v1/ai/call`)
2. Database persistence layer
3. Policy engine integration
4. Offline verifier CLI enhancements
