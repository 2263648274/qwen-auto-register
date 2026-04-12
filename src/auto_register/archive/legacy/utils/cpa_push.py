"""Push successful registration data to CPA/CLI proxy backend."""

import os
import socket
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def push_cpa_registration(
    *,
    email: str,
    password: str,
    access: str,
    refresh: str,
    expires: int,
    auth_profiles_path: str,
    on_log: Optional[Callable[[str], None]] = None,
) -> bool:
    """Push account and token data to configured CPA backend.

    Returns True when any configured endpoint accepts the payload.
    """
    log = on_log or (lambda _: None)

    if not _env_bool("CLI_PROXY_API_ENABLED", True):
        log("[CPA] 已禁用自动推送（CLI_PROXY_API_ENABLED=0）")
        return False

    base_url = (os.environ.get("CLI_PROXY_API_BASE_URL") or "").strip().rstrip("/")
    api_key = (os.environ.get("CLI_PROXY_API_KEY") or "").strip()
    if not base_url or not api_key:
        log("[CPA] 未配置 CLI_PROXY_API_BASE_URL 或 CLI_PROXY_API_KEY，跳过推送")
        return False

    full_url = (os.environ.get("CLI_PROXY_API_PUSH_URL") or "").strip()
    if full_url:
        urls = [full_url]
    else:
        paths_raw = (os.environ.get("CLI_PROXY_API_PUSH_PATHS") or "").strip()
        if paths_raw:
            paths = [p.strip() for p in paths_raw.split(",") if p.strip()]
        else:
            single_path = (os.environ.get("CLI_PROXY_API_PUSH_PATH") or "/api/cpa/push").strip()
            paths = [single_path]
        urls = [_join_url(base_url, p) for p in paths]

    request_id = str(uuid.uuid4())
    payload = {
        "provider": "qwen",
        "email": email,
        "password": password,
        "accessToken": access,
        "refreshToken": refresh,
        "expires": expires,
        "authProfilesPath": auth_profiles_path,
        "source": "qwen-auto-register",
        "requestId": request_id,
        "hostname": socket.gethostname(),
        "createdAt": _now_iso_utc(),
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-API-Key": api_key,
        "x-api-key": api_key,
    }

    timeout = float((os.environ.get("CLI_PROXY_API_TIMEOUT") or "15").strip() or "15")
    retries = int((os.environ.get("CLI_PROXY_API_RETRIES") or "2").strip() or "2")

    for url in urls:
        for i in range(retries + 1):
            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(url, json=payload, headers=headers)

                if 200 <= resp.status_code < 300:
                    try:
                        body = resp.json()
                    except Exception:
                        body = None

                    if isinstance(body, dict):
                        code = body.get("code")
                        success = body.get("success")
                        if code in (None, 200) and success is not False:
                            log(f"[CPA] 推送成功: {url}")
                            return True
                    else:
                        log(f"[CPA] 推送成功: {url}")
                        return True

                    err_msg = (body.get("message") if isinstance(body, dict) else "unknown")
                    log(f"[CPA] 推送返回业务失败: {url} message={err_msg}")
                else:
                    log(f"[CPA] 推送失败: {url} HTTP {resp.status_code}")
            except Exception as e:
                log(f"[CPA] 推送异常: {url} ({e})")

            if i < retries:
                time.sleep(1.0)

    return False
