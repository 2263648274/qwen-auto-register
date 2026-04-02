"""Write Qwen OAuth credentials to auth-profiles.json."""

import json
import os
from pathlib import Path
from typing import Any


def get_default_auth_profiles_path() -> Path:
    """Get default auth-profiles.json path."""
    path = os.environ.get("OPENCLAW_AUTH_PROFILES_PATH")
    if path:
        return Path(path)
    home = Path.home()
    return home / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"


class AuthProfilesWriter:
    """Write qwen-portal:default profile to auth-profiles.json."""

    PROFILE_KEY = "qwen-portal:default"

    def __init__(self, path: Path | str | None = None):
        """Initialize with optional custom path."""
        self._path = Path(path) if path else get_default_auth_profiles_path()

    @property
    def path(self) -> Path:
        """Get target auth-profiles path."""
        return self._path

    def write_qwen_profile(
        self,
        access: str,
        refresh: str,
        expires: int,
    ) -> None:
        """Update or create qwen-portal:default profile, preserving other data.

        Args:
            access: Access token.
            refresh: Refresh token.
            expires: Expiration as milliseconds Unix timestamp (13 digits).
        """
        data = self._load()
        if "profiles" not in data:
            data["profiles"] = {}

        data["profiles"][self.PROFILE_KEY] = {
            "type": "oauth",
            "provider": "qwen-portal",
            "access": access,
            "refresh": refresh,
            "expires": expires,
        }

        # Ensure lastGood and usageStats exist for OpenClaw
        if "lastGood" not in data:
            data["lastGood"] = {}
        data["lastGood"]["qwen-portal"] = self.PROFILE_KEY

        if "usageStats" not in data:
            data["usageStats"] = {}
        if self.PROFILE_KEY not in data["usageStats"]:
            data["usageStats"][self.PROFILE_KEY] = {
                "errorCount": 0,
                "lastUsed": expires,
            }

        self._save(data)

    def _load(self) -> dict[str, Any]:
        """Load existing auth-profiles or return minimal structure."""
        if not self._path.exists():
            return {"version": 1, "profiles": {}}

        with open(self._path, encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict[str, Any]) -> None:
        """Save data to file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
