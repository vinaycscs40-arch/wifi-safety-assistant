"""
Security & Guardrails Module
Implements: input validation, PII protection, prompt injection detection,
rate limiting, output validation, and safe handling of cybersecurity requests.
"""
import re
import time
import html
import logging
from typing import Dict, Any, List, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PII patterns to detect and block
# ---------------------------------------------------------------------------
PII_PATTERNS = {
    "phone_number": re.compile(r"\b[6-9]\d{9}\b"),
    "aadhaar": re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
    "pan_card": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b"),
    "password_hint": re.compile(
        r"\b(password|passwd|pwd|secret|credential|pin)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    "bank_account": re.compile(r"\b\d{9,18}\b"),  # generic bank account
    "email_in_context": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "ifsc_code": re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
}

# ---------------------------------------------------------------------------
# Prompt injection patterns
# ---------------------------------------------------------------------------
INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+previous\s+instructions",
        r"ignore\s+all\s+instructions",
        r"disregard\s+(your|the)\s+(previous|above|prior)",
        r"you\s+are\s+now\s+a",
        r"act\s+as\s+(a\s+)?(different|new|evil|hacker|malicious)",
        r"jailbreak",
        r"dan\s+mode",
        r"developer\s+mode",
        r"system\s+prompt",
        r"reveal\s+your\s+instructions",
        r"print\s+your\s+system\s+prompt",
        r"\\n\\n(human|assistant|user):",
        r"</?system>",
        r"</?prompt>",
    ]
]

# ---------------------------------------------------------------------------
# Dangerous request patterns (things we must never do)
# ---------------------------------------------------------------------------
DANGEROUS_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"scan\s+(the\s+)?network",
        r"nmap",
        r"ping\s+sweep",
        r"port\s+scan",
        r"vulnerability\s+scan",
        r"exploit",
        r"hack\s+(the\s+)?network",
        r"attack\s+(the\s+)?router",
        r"brute\s+force",
        r"crack\s+(the\s+)?(password|wifi)",
        r"intercept\s+(traffic|packets)",
        r"sniff\s+(traffic|packets)",
    ]
]

# ---------------------------------------------------------------------------
# Input length and content limits
# ---------------------------------------------------------------------------
MAX_FIELD_LENGTHS = {
    "wifi_name": 100,
    "connection_type": 50,
    "location": 200,
    "user_context": 1000,
}

ALLOWED_CONNECTION_TYPES = {
    "open", "wep", "wpa", "wpa2", "wpa2-personal", "wpa2-enterprise",
    "wpa3", "wpa3-personal", "wpa3-enterprise", "802.1x", "unknown", "other",
    "unsecured", "none", "secured",
}


class RateLimiter:
    """Simple in-memory token bucket rate limiter."""

    def __init__(self, max_requests_per_minute: int = 30):
        self.max_rpm = max_requests_per_minute
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, client_id: str) -> Tuple[bool, int]:
        """
        Returns (allowed, requests_remaining).
        """
        now = time.time()
        window = 60.0  # 1 minute
        self._requests[client_id] = [
            t for t in self._requests[client_id] if now - t < window
        ]
        count = len(self._requests[client_id])
        if count >= self.max_rpm:
            return False, 0
        self._requests[client_id].append(now)
        return True, self.max_rpm - count - 1


class OutputValidator:
    """Validates AI model output before returning to users."""

    HALLUCINATION_TRIGGERS = [
        re.compile(p, re.IGNORECASE)
        for p in [
            r"as\s+an\s+ai\s+language\s+model\s+i\s+cannot",
            r"i\s+(will|can)\s+hack",
            r"i\s+have\s+scanned\s+the\s+network",
            r"the\s+network\s+is\s+100%\s+safe",
            r"guaranteed\s+safe",
            r"no\s+risk\s+whatsoever",
        ]
    ]

    REQUIRED_DISCLAIMER = (
        "Note: This assessment is based on user-provided information only. "
        "No network scanning or testing was performed."
    )

    def validate(self, text: str, risk_level: str) -> Dict[str, Any]:
        """
        Returns {valid, issues, sanitized_text}
        """
        issues = []
        sanitized = text

        # Check for hallucination triggers
        for pat in self.HALLUCINATION_TRIGGERS:
            if pat.search(text):
                issues.append(f"Hallucination trigger detected: {pat.pattern[:40]}")

        # Strip any leaked PII from outputs
        for name, pat in PII_PATTERNS.items():
            if name in ("phone_number", "aadhaar", "credit_card", "password_hint"):
                sanitized = pat.sub(f"[{name.upper()} REDACTED]", sanitized)

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "sanitized_text": sanitized,
        }


class Guardrails:
    """
    Main guardrails class used by the Supervisor.
    Validates inputs before passing to agents.
    """

    def __init__(self, max_requests_per_minute: int = 30, enable: bool = True):
        self.enabled = enable
        self.rate_limiter = RateLimiter(max_requests_per_minute)
        self.output_validator = OutputValidator()
        logger.info(f"Guardrails initialized (enabled={enable})")

    def validate_input(
        self,
        wifi_name: str,
        connection_type: str,
        location: str,
        user_context: str,
        client_ip: str = "unknown",
    ) -> Dict[str, Any]:
        """
        Full input validation pipeline.
        Returns {allowed, reason, flags, sanitized_inputs}
        """
        if not self.enabled:
            return {
                "allowed": True,
                "reason": "Guardrails disabled",
                "flags": [],
                "sanitized": {
                    "wifi_name": wifi_name,
                    "connection_type": connection_type,
                    "location": location,
                    "user_context": user_context,
                },
            }

        flags: List[str] = []

        # 1. Rate limiting
        allowed, remaining = self.rate_limiter.is_allowed(client_ip)
        if not allowed:
            return {
                "allowed": False,
                "reason": "Rate limit exceeded. Please wait before trying again.",
                "flags": ["rate_limit"],
            }

        # 2. Required field check
        if not wifi_name or not wifi_name.strip():
            return {
                "allowed": False,
                "reason": "Wi-Fi network name is required",
                "flags": ["missing_required_field"],
            }

        # 3. Field length validation
        inputs = {
            "wifi_name": wifi_name or "",
            "connection_type": connection_type or "",
            "location": location or "",
            "user_context": user_context or "",
        }
        for field, max_len in MAX_FIELD_LENGTHS.items():
            if len(inputs[field]) > max_len:
                inputs[field] = inputs[field][:max_len]
                flags.append(f"field_truncated:{field}")

        # 4. Normalize and validate connection_type
        raw_ct = inputs["connection_type"].lower().strip()
        if raw_ct and raw_ct not in ALLOWED_CONNECTION_TYPES:
            inputs["connection_type"] = "unknown"
            flags.append("connection_type_normalized")

        # 5. Sanitize (strip HTML entities)
        sanitized = {k: html.escape(v.strip()) for k, v in inputs.items()}

        # 6. Prompt injection detection
        full_text = " ".join(sanitized.values())
        for pat in INJECTION_PATTERNS:
            if pat.search(full_text):
                logger.warning(f"Prompt injection attempt from {client_ip}: {pat.pattern[:50]}")
                return {
                    "allowed": False,
                    "reason": "Invalid input detected. Please describe your Wi-Fi connection normally.",
                    "flags": ["prompt_injection"],
                }

        # 7. Dangerous request detection
        for pat in DANGEROUS_PATTERNS:
            if pat.search(full_text):
                logger.warning(f"Dangerous request from {client_ip}: {pat.pattern[:50]}")
                return {
                    "allowed": False,
                    "reason": (
                        "This application does not perform network scanning or testing. "
                        "Please describe your Wi-Fi connection details for a safety assessment."
                    ),
                    "flags": ["dangerous_request"],
                }

        # 8. PII detection (flag but allow, with PII stripped)
        pii_found = []
        for name, pat in PII_PATTERNS.items():
            # Only block passwords; flag others
            if name == "password_hint":
                if pat.search(sanitized.get("user_context", "")):
                    pii_found.append(name)
                    sanitized["user_context"] = pat.sub("[PASSWORD REDACTED]",
                                                        sanitized["user_context"])
                    flags.append(f"pii_redacted:{name}")
            elif name in ("aadhaar", "credit_card", "pan_card"):
                if pat.search(full_text):
                    pii_found.append(name)
                    flags.append(f"pii_detected:{name}")
                    # Redact from context
                    sanitized["user_context"] = pat.sub(
                        f"[{name.upper()} REDACTED]", sanitized["user_context"]
                    )

        if "aadhaar" in pii_found or "credit_card" in pii_found:
            logger.warning(f"PII detected from {client_ip}: {pii_found}")

        return {
            "allowed": True,
            "reason": "Input validated",
            "flags": flags,
            "sanitized": sanitized,
            "rate_limit_remaining": remaining,
        }

    def validate_output(self, text: str, risk_level: str) -> Dict[str, Any]:
        return self.output_validator.validate(text, risk_level)
