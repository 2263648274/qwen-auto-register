"""Qwen OAuth 2.0 设备码流程，获取 portal API token（与 openclaw onboard 一致）。"""

import base64
import hashlib
import json
import os
import re
import shlex
import subprocess
import uuid
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

# 与 OpenClaw qwen-portal-auth 一致
QWEN_OAUTH_BASE = "https://chat.qwen.ai"
DEVICE_CODE_URL = f"{QWEN_OAUTH_BASE}/api/v1/oauth2/device/code"
TOKEN_URL = f"{QWEN_OAUTH_BASE}/api/v1/oauth2/token"
CLIENT_ID = "f0304373b74a44d2b584a3fb70ca9e56"
SCOPE = "openid profile email model.completion"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"


def _pkce() -> tuple[str, str]:
    """生成 PKCE verifier 与 challenge (base64url)。"""
    verifier = secrets.token_urlsafe(32)
    challenge = hashlib.sha256(verifier.encode()).digest()
    challenge_b64 = base64.urlsafe_b64encode(challenge).decode().rstrip("=")
    return verifier, challenge_b64


def request_device_code(page: Optional[object] = None) -> dict:
    """请求设备码，返回 {device_code, user_code, verification_uri, ...}。page 为 Playwright Page 时在浏览器内请求以通过 WAF。"""
    verifier, challenge = _pkce()
    body = {
        "client_id": CLIENT_ID,
        "scope": SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    body_str = urllib.parse.urlencode(body)

    if page is not None:
        # 在浏览器上下文中请求，携带 chat.qwen.ai 的 cookie，通过 WAF
        script = """
        async ([url, body, requestId]) => {
            const r = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "x-request-id": requestId },
                body: body
            });
            return { status: r.status, text: await r.text() };
        }
        """
        result = page.evaluate(script, [DEVICE_CODE_URL, body_str, str(uuid.uuid4())])
        if result["status"] != 200:
            raise ValueError(f"设备码请求失败: HTTP {result['status']}")
        raw = result["text"]
    else:
        req = urllib.request.Request(
            DEVICE_CODE_URL,
            data=body_str.encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "x-request-id": str(uuid.uuid4()),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()

    if not raw.strip():
        raise ValueError("设备码接口返回空响应")
    out = json.loads(raw)
    out["_verifier"] = verifier
    return out


def poll_token(device_code: str, code_verifier: str, page: Optional[object] = None) -> tuple[str, dict | None]:
    """
    轮询 token 端点。page 为 Playwright Page 时在浏览器内请求。
    返回 (status, result):
      ("pending", None) - 等待授权
      ("pending", {"slow_down": True}) - 等待授权，需降低轮询频率
      ("success", dict) - 成功
      ("error", {"message": ...}) - 失败
    """
    body = {
        "grant_type": GRANT_TYPE,
        "client_id": CLIENT_ID,
        "device_code": device_code,
        "code_verifier": code_verifier,
    }
    body_str = urllib.parse.urlencode(body)

    if page is not None:
        script = """
        async ([url, body]) => {
            const r = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json" },
                body: body
            });
            return { status: r.status, text: await r.text() };
        }
        """
        result = page.evaluate(script, [TOKEN_URL, body_str])
        raw = result["text"]
        try:
            payload = json.loads(raw)
        except Exception:
            if result["status"] != 200:
                return "error", {"message": f"HTTP {result['status']}: {raw[:200]}"}
            raise
        if result["status"] != 200:
            err = payload.get("error", "")
            if err == "authorization_pending":
                return "pending", None
            if err == "slow_down":
                return "pending", {"slow_down": True}
            return "error", {"message": payload.get("error_description") or payload.get("error") or str(result["status"])}
    else:
        req = urllib.request.Request(
            TOKEN_URL,
            data=body_str.encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read().decode())
            except Exception:
                return "error", {"message": str(e)}
            err = payload.get("error", "")
            if err == "authorization_pending":
                return "pending", None
            if err == "slow_down":
                return "pending", {"slow_down": True}
            return "error", {"message": payload.get("error_description") or payload.get("error") or str(e)}

    # 成功响应 (HTTP 200)，解析 token
    err = payload.get("error", "")
    if err == "authorization_pending":
        return "pending", None
    if err == "slow_down":
        return "pending", {"slow_down": True}
    if err:
        return "error", {"message": payload.get("error_description") or payload.get("error") or err}

    acc = payload.get("access_token") or payload.get("access")
    ref = payload.get("refresh_token") or payload.get("refresh")
    exp = payload.get("expires_in")
    if not acc or not ref:
        return "error", {"message": "OAuth 返回的 token 不完整"}
    expires = int(time.time() * 1000) + (int(exp) * 1000) if exp else int(time.time() * 1000) + 30 * 24 * 60 * 60 * 1000
    result = {"access": acc, "refresh": ref, "expires": expires}
    if payload.get("resource_url"):
        result["resource_url"] = payload["resource_url"]
    return "success", result


def run_device_code_flow(
    open_verification_url: Callable[[str, str], None],
    on_wait: Optional[Callable[[], None]] = None,
    poll_interval: float = 2.0,
    timeout_seconds: float = 300.0,
    page_for_requests: Optional[object] = None,
) -> Optional[dict]:
    """
    执行设备码 OAuth 流程，获取 API token（与 openclaw onboard 一致格式）。
    - open_verification_url: 接收 (url, user_code)，打开授权页（用户需已登录 chat.qwen.ai）
    - on_wait: 可选，轮询时回调
    - page_for_requests: Playwright Page，在浏览器上下文中请求以通过 WAF（可选）
    返回 {access, refresh, expires} 或 None
    """
    dev = request_device_code(page=page_for_requests)
    dc = dev.get("device_code")
    uc = dev.get("user_code")
    uri = dev.get("verification_uri_complete") or dev.get("verification_uri")
    verifier = dev.get("_verifier", "")
    exp_in = int(dev.get("expires_in", 900))
    interval = max(float(dev.get("interval", 2)), poll_interval)

    if not dc or not uc or not uri or not verifier:
        return None

    open_verification_url(uri, uc)

    deadline = time.time() + min(timeout_seconds, exp_in)
    while time.time() < deadline:
        status, result = poll_token(dc, verifier, page=page_for_requests)
        if status == "success" and result:
            return result
        if status == "error":
            return None
        # RFC 8628: 收到 slow_down 时增加轮询间隔，避免触发限流
        if status == "pending" and result and result.get("slow_down"):
            interval = min(interval * 1.5, 10.0)
        if on_wait:
            on_wait()
        time.sleep(interval)
    return None


def _extract_first_url(text: str) -> Optional[str]:
    """Extract first http/https URL from text."""
    match = re.search(r"https?://[^\s\"'<>]+", text)
    return match.group(0) if match else None


def _parse_token_blob(text: str) -> Optional[dict[str, str | int]]:
    """Parse token-like JSON blobs from cli output when available."""
    for candidate in re.findall(r"\{[^{}]*\}", text):
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        access = payload.get("access_token") or payload.get("access")
        refresh = payload.get("refresh_token") or payload.get("refresh")
        expires_in = payload.get("expires_in") or payload.get("expires")
        if access and refresh:
            expires = int(time.time() * 1000)
            if isinstance(expires_in, int):
                expires += expires_in * 1000 if expires_in < 10_000_000_000 else expires_in
            elif isinstance(expires_in, str) and expires_in.isdigit():
                value = int(expires_in)
                expires += value * 1000 if value < 10_000_000_000 else value
            else:
                expires += 30 * 24 * 60 * 60 * 1000
            return {"access": access, "refresh": refresh, "expires": expires}
    return None


def run_cli_proxy_login_flow(
    open_verification_url: Callable[[str, str], None],
    on_wait: Optional[Callable[[], None]] = None,
    command: Optional[str] = None,
    timeout_seconds: float = 300.0,
) -> Optional[dict[str, str | int]]:
    """Run cli-proxy-api Qwen login flow and try to extract tokens from its output.

    This is a best-effort adapter for external login commands that print a login URL
    and then continue until authorization is finished.
    """
    cmd = (command or os.environ.get("CLI_PROXY_API_LOGIN_CMD") or "cli-proxy-api --qwen-login --no-browser").strip()
    if not cmd:
        return None

    args = shlex.split(cmd, posix=(os.name != "nt"))
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception:
        return None

    assert proc.stdout is not None
    collected: list[str] = []
    opened_url = False
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        line = proc.stdout.readline()
        if line:
            collected.append(line)
            if not opened_url:
                url = _extract_first_url(line)
                if url:
                    open_verification_url(url, "")
                    opened_url = True

            parsed = _parse_token_blob("".join(collected))
            if parsed:
                proc.terminate()
                return parsed

        if proc.poll() is not None:
            break

        if on_wait:
            on_wait()
        time.sleep(1.0)

    try:
        tail = proc.stdout.read()
        if tail:
            collected.append(tail)
    except Exception:
        pass

    parsed = _parse_token_blob("".join(collected))
    if parsed:
        return parsed

    if not opened_url:
        text = "".join(collected)
        url = _extract_first_url(text)
        if url:
            open_verification_url(url, "")

    return None
