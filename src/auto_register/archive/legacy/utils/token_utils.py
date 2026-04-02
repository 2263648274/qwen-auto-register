"""JWT 解码与 Token 验证工具。"""

import base64
import json
import time
from typing import Optional


def is_valid_jwt(token: str) -> bool:
    """验证是否为有效 JWT 格式（OpenClaw qwen-portal 需要 JWT）。"""
    if not token or not isinstance(token, str):
        return False
    parts = token.split(".")
    if len(parts) != 3:
        return False
    if not token.startswith("eyJ"):
        return False
    return decode_jwt_payload(token) is not None


def decode_jwt_payload(token: str) -> Optional[dict]:
    """解码 JWT payload，返回 payload 字典或 None。

    JWT 格式: header.payload.signature
    payload 为 base64url 编码的 JSON。
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        decoded = base64.urlsafe_b64decode(payload_b64)
        return json.loads(decoded)
    except Exception:
        return None


def get_expires_from_jwt(access_token: str) -> Optional[int]:
    """从 JWT access token 解析过期时间，返回毫秒时间戳。

    若 JWT 包含 exp 字段（秒级 Unix 时间戳），返回 exp * 1000。
    否则返回 None。
    """
    payload = decode_jwt_payload(access_token)
    if not payload or "exp" not in payload:
        return None
    try:
        exp_sec = int(payload["exp"])
        return exp_sec * 1000
    except (TypeError, ValueError):
        return None


def validate_tokens(
    access: str,
    refresh: str,
    allow_same: bool = False,
    allow_api_token: bool = False,
) -> None:
    """验证 access 和 refresh token。

    校验：
    - access 与 refresh 不能为空
    - access 与 refresh 必须不同（allow_same=True 时可相同）
    - allow_api_token=False 时要求 JWT 格式；True 时接受 OAuth API token（base64 等）

    Args:
        allow_same: 为 True 时允许 access == refresh
        allow_api_token: 为 True 时接受非 JWT 格式（如 OAuth 设备码返回的 API token）

    Raises:
        ValueError: 验证失败时
    """
    if not access or not refresh:
        raise ValueError("Access 和 Refresh Token 不能为空")
    if access == refresh and not allow_same:
        raise ValueError("Access 和 Refresh Token 不能相同")
    if not allow_api_token:
        for name, tok in [("Access", access), ("Refresh", refresh)]:
            if tok.count(".") != 2:
                raise ValueError(f"{name} Token 格式错误（需为 JWT 三段式）")
