"""
secrets_loader.py — Shared AWS Secrets Manager loader for ThinkVelocity Python services.

Usage:
    from configs.secrets.python.secrets_loader import init_secrets
    init_secrets("thinkvelocity/production/python-ai")

Call init_secrets() at the very top of main.py / app.py, before any other
imports that read environment variables (e.g., before pydantic Settings classes
are instantiated or before `from config import settings`).

Falls back gracefully to os.environ / python-dotenv when:
  - boto3 is not installed (local dev without AWS SDK)
  - AWS credentials are not configured (local dev)
  - The secret does not exist (first-time dev setup)
  - Any other AWS error

AWS region: ap-south-1
Secret format: JSON object with all env vars for the service as string key/value pairs.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Module-level cache: secret_name -> {key: value} dict
# Populated on first call to load_secrets(); subsequent calls return from cache.
_SECRETS_CACHE: Dict[str, Dict[str, str]] = {}

# Track which source was used so callers / health checks can inspect it.
_SOURCE: Optional[str] = None  # "aws_secrets_manager" | "env_file" | "os_environ"


def load_secrets(secret_name: str) -> Dict[str, str]:
    """
    Fetch a JSON secret from AWS Secrets Manager and return it as a dict.

    The result is cached at module level — AWS is contacted only once per
    process lifetime regardless of how many times load_secrets() is called
    with the same secret_name.

    Falls back to an empty dict (so the caller can continue from os.environ)
    when boto3 is unavailable or AWS is unreachable.

    Args:
        secret_name: Full secret path, e.g. "thinkvelocity/production/python-ai"

    Returns:
        Dict of secret key/value pairs (all strings), or {} on failure.
    """
    global _SOURCE

    if secret_name in _SECRETS_CACHE:
        logger.debug("secrets_loader: returning cached secrets for '%s'", secret_name)
        return _SECRETS_CACHE[secret_name]

    # ── 1. Try AWS Secrets Manager ──────────────────────────────────────────
    try:
        import boto3  # noqa: PLC0415  (deferred import intentional)
        from botocore.exceptions import (  # noqa: PLC0415
            ClientError,
            NoCredentialsError,
            NoRegionError,
        )

        region = os.environ.get("AWS_REGION", "ap-south-1")
        client = boto3.client("secretsmanager", region_name=region)

        response = client.get_secret_value(SecretId=secret_name)
        raw = response.get("SecretString") or ""
        secrets: Dict[str, str] = json.loads(raw)

        if not isinstance(secrets, dict):
            raise ValueError(
                f"Secret '{secret_name}' is not a JSON object — got {type(secrets).__name__}"
            )

        _SECRETS_CACHE[secret_name] = {str(k): str(v) for k, v in secrets.items()}
        _SOURCE = "aws_secrets_manager"
        logger.info(
            "secrets_loader: loaded %d secrets from AWS Secrets Manager ('%s')",
            len(secrets),
            secret_name,
        )
        return _SECRETS_CACHE[secret_name]

    except ImportError:
        logger.info(
            "secrets_loader: boto3 not installed — falling back to env file / os.environ"
        )
    except NoCredentialsError:
        logger.info(
            "secrets_loader: no AWS credentials found — falling back to env file / os.environ"
        )
    except NoRegionError:
        logger.info(
            "secrets_loader: no AWS region configured — falling back to env file / os.environ"
        )
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code in ("ResourceNotFoundException", "InvalidParameterException"):
            logger.warning(
                "secrets_loader: secret '%s' not found in AWS SM (code=%s) "
                "— falling back to env file / os.environ",
                secret_name,
                error_code,
            )
        else:
            logger.warning(
                "secrets_loader: AWS SM ClientError for '%s' (code=%s): %s "
                "— falling back to env file / os.environ",
                secret_name,
                error_code,
                exc,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "secrets_loader: unexpected error fetching '%s': %s "
            "— falling back to env file / os.environ",
            secret_name,
            exc,
        )

    # ── 2. Fallback: empty dict; caller will use os.environ as-is ───────────
    _SECRETS_CACHE[secret_name] = {}
    _SOURCE = "env_file"
    return {}


def init_secrets(service_name: str) -> None:
    """
    Load secrets for *service_name* from AWS Secrets Manager and merge them
    into os.environ so that all subsequent code (pydantic Settings, os.getenv,
    etc.) sees the production values without any other changes.

    Existing os.environ values are NOT overwritten — AWS SM values are only
    injected for keys that are not already present. This lets Docker /
    Kubernetes environment variable overrides take precedence when needed.

    Args:
        service_name: Full secret path, e.g. "thinkvelocity/production/python-ai"
                      or just the service portion "python-ai" (the prefix
                      "thinkvelocity/production/" is added automatically when
                      the path does not already start with "thinkvelocity/").
    """
    global _SOURCE

    # Normalise: accept both "python-ai" and the full path
    if not service_name.startswith("thinkvelocity/"):
        secret_name = f"thinkvelocity/production/{service_name}"
    else:
        secret_name = service_name

    secrets = load_secrets(secret_name)

    if not secrets:
        # AWS SM unavailable — load .env file as fallback
        _try_load_dotenv()
        _SOURCE = "env_file" if _dotenv_loaded() else "os_environ"
        logger.info(
            "secrets_loader: using source='%s' (AWS SM not available)", _SOURCE
        )
        return

    injected = 0
    skipped = 0
    for key, value in secrets.items():
        if key not in os.environ:
            os.environ[key] = value
            injected += 1
        else:
            skipped += 1

    logger.info(
        "secrets_loader: injected %d secrets into os.environ from AWS SM "
        "('%s'); skipped %d keys already present in environment",
        injected,
        secret_name,
        skipped,
    )
    _SOURCE = "aws_secrets_manager"


def get_source() -> Optional[str]:
    """Return which source was used: 'aws_secrets_manager', 'env_file', or 'os_environ'."""
    return _SOURCE


# ── Internal helpers ────────────────────────────────────────────────────────

_DOTENV_ATTEMPTED = False
_DOTENV_SUCCESS = False


def _try_load_dotenv() -> None:
    """Best-effort python-dotenv load; silently skipped if not installed."""
    global _DOTENV_ATTEMPTED, _DOTENV_SUCCESS
    if _DOTENV_ATTEMPTED:
        return
    _DOTENV_ATTEMPTED = True
    try:
        from dotenv import load_dotenv  # noqa: PLC0415

        loaded = load_dotenv(override=False)  # don't overwrite existing env vars
        _DOTENV_SUCCESS = bool(loaded)
        if loaded:
            logger.info("secrets_loader: loaded .env file via python-dotenv")
        else:
            logger.debug("secrets_loader: no .env file found (python-dotenv)")
    except ImportError:
        logger.debug("secrets_loader: python-dotenv not installed; skipping .env load")


def _dotenv_loaded() -> bool:
    return _DOTENV_SUCCESS
