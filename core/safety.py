import re

_PATTERNS = [
    (r'sk-[A-Za-z0-9]{16,}', 'api_key'),
    (r'pk_(?:live|test)_[A-Za-z0-9]{16,}|pk_[A-Za-z0-9]{16,}', 'api_key'),
    (r'Bearer\s+[A-Za-z0-9\-._~+/]{20,}', 'bearer_token'),
    (r'-----BEGIN\s+\w+\s+KEY-----[\s\S]*?-----END\s+\w+\s+KEY-----', 'private_key'),
    (r'10\.\d{1,3}\.\d{1,3}\.\d{1,3}', 'internal_ip'),
    (r'192\.168\.\d{1,3}\.\d{1,3}', 'internal_ip'),
    (r'172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}', 'internal_ip'),
    (r'[A-Za-z0-9+/]{40,}={0,2}(?=\s|$)', 'high_entropy_token'),
]


def redact(text: str) -> tuple[str, list[str]]:
    redacted = text
    found: list[str] = []
    for pattern, label in _PATTERNS:
        matches = re.findall(pattern, redacted)
        if matches:
            found.append(label)
            redacted = re.sub(pattern, '[REDACTED]', redacted)
    return redacted, found
