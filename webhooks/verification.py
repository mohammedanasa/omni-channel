import hashlib
import hmac


def generate_hmac_signature(payload: bytes, secret: str) -> str:
    """Generate HMAC-SHA256 signature for outbound webhook payloads."""
    return hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


def verify_hmac_signature(payload: bytes, secret: str, signature: str) -> bool:
    """Verify an inbound HMAC-SHA256 signature."""
    expected = generate_hmac_signature(payload, secret)
    return hmac.compare_digest(expected, signature)
