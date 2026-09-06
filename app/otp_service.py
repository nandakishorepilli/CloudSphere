"""OTP generation and delivery boundary for Cloud Sphere.

Replace ``send_otp`` with an email-provider implementation for production.
"""
import hashlib
import logging
import os
import secrets

logger = logging.getLogger(__name__)
OTP_TTL_MINUTES = 5
MAX_OTP_ATTEMPTS = 5
DEVELOPMENT_MODE = os.getenv("CLOUDSPHERE_ENV", "development").lower() != "production"


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def send_otp(email: str, code: str) -> None:
    """Deliver an OTP. Development mode logs it; production must use an email provider."""
    if DEVELOPMENT_MODE:
        logger.warning("Development OTP for %s: %s", email, code)
        return
    raise RuntimeError("No production email provider has been configured.")
