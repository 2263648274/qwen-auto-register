"""CLI Proxy management API helpers for remote Qwen auth flow."""

import time
from typing import Any, Callable, Optional

import httpx


def _headers(key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _join(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def get_qwen_auth_url(base_url: str, management_key: str, timeout: float = 20.0) -> tuple[str, str]:
    """Get Qwen auth URL and state from remote management API."""
    url = _join(base_url, "/v0/management/qwen-auth-url")
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, headers=_headers(management_key))
        resp.raise_for_status()
        data = resp.json()

    auth_url = (data.get("url") or "").strip()
    state = (data.get("state") or "").strip()
    status = (data.get("status") or "").strip().lower()
    if status not in ("ok", "success") or not auth_url or not state:
        raise RuntimeError(f"Invalid qwen-auth-url response: {data}")
    return auth_url, state


def poll_auth_status(
    base_url: str,
    management_key: str,
    state: str,
    poll_interval: float = 2.0,
    timeout_seconds: float = 300.0,
    on_wait: Optional[Callable[[], None]] = None,
) -> tuple[bool, Optional[str]]:
    """Poll auth status until ok/error/timeout.

    Returns (success, error_message).
    """
    url = _join(base_url, f"/v0/management/get-auth-status?state={state}")
    deadline = time.time() + timeout_seconds

    with httpx.Client(timeout=20.0) as client:
        while time.time() < deadline:
            try:
                resp = client.get(url, headers=_headers(management_key))
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                return False, f"poll status request failed: {e}"

            status = str(data.get("status") or "").strip().lower()
            if status == "ok":
                return True, None
            if status == "error":
                return False, str(data.get("error") or "auth failed")

            if on_wait:
                on_wait()
            time.sleep(poll_interval)

    return False, "poll auth status timeout"


def list_auth_files(base_url: str, management_key: str, timeout: float = 20.0) -> list[dict[str, Any]]:
    """List auth files from management API."""
    url = _join(base_url, "/v0/management/auth-files")
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, headers=_headers(management_key))
        resp.raise_for_status()
        data = resp.json()
    files = data.get("files")
    return files if isinstance(files, list) else []
