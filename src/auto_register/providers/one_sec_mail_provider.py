"""Temporary email providers. Supports Mail.tm (default) and 1secMail."""

import json
import os
import random
import re
import string
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx

def get_email_provider(
    poll_interval: float = 5.0,
    timeout: float = 120.0,
):
    """Get the configured temporary email provider."""
    provider = os.environ.get("AUTO_REGISTER_EMAIL_PROVIDER", "mailtm").lower().strip()
    if provider in ("cloudflare", "cloudmail", "mailcraft"):
        return CloudMailProvider(poll_interval=poll_interval, timeout=timeout)
    if provider == "1secmail":
        return OneSecMailProvider(poll_interval=poll_interval, timeout=timeout)
    return MailTmProvider(poll_interval=poll_interval, timeout=timeout)


def _extract_activation_url_from_text(text: str) -> Optional[str]:
    """Extract first https activation URL from text."""
    url_pattern = r"https://[^\s<>\"']+"
    urls = re.findall(url_pattern, text)
    for url in urls:
        lower = url.lower()
        if any(kw in lower for kw in ("verify", "activate", "confirm", "token", "auth")):
            return url
    return urls[0] if urls else None


# --- Mail.tm (default, no 403) ---
_MAILTM_BASE = "https://api.mail.tm"


class MailTmProvider:
    """Temporary email via Mail.tm API. No API key, no 403 issues."""

    def __init__(self, poll_interval: float = 5.0, timeout: float = 120.0):
        self._poll_interval = poll_interval
        self._timeout = timeout
        self._email: Optional[str] = None
        self._password: Optional[str] = None

    def generate_email(self) -> str:
        """Create Mail.tm account and return email."""
        with httpx.Client(timeout=30) as client:
            r = client.get(f"{_MAILTM_BASE}/domains")
            r.raise_for_status()
            data = r.json()
            domains = [
                d["domain"] for d in data.get("hydra:member", [])
                if d.get("domain")
            ]
            if not domains:
                raise RuntimeError("Mail.tm: no domains available")
            domain = random.choice(domains)
            login = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
            self._password = "".join(random.choices(string.ascii_letters + string.digits, k=16))
            address = f"{login}@{domain}"
            r2 = client.post(
                f"{_MAILTM_BASE}/accounts",
                json={"address": address, "password": self._password},
                headers={"Content-Type": "application/json"},
            )
            r2.raise_for_status()
            self._email = address
            return address

    def wait_for_activation_link(
        self,
        email: str,
        subject_contains: Optional[str] = None,
        from_contains: Optional[str] = None,
    ) -> str:
        """Poll Mail.tm for activation email and extract link."""
        pw = self._password if email == self._email else None
        if not pw:
            raise ValueError("MailTmProvider: must call generate_email first for this address")
        with httpx.Client(timeout=30) as client:
            r = client.post(
                f"{_MAILTM_BASE}/token",
                json={"address": email, "password": pw},
                headers={"Content-Type": "application/json"},
            )
            r.raise_for_status()
            token = r.json()["token"]
        start = time.time()
        seen_ids: set[str] = set()
        headers = {"Authorization": f"Bearer {token}"}
        while (time.time() - start) < self._timeout:
            with httpx.Client(timeout=30) as c:
                r = c.get(f"{_MAILTM_BASE}/messages", headers=headers)
                r.raise_for_status()
                items = r.json().get("hydra:member", [])
            for msg in items:
                mid = msg.get("id")
                if mid in seen_ids:
                    continue
                subj = (msg.get("subject") or "").lower()
                from_addr = (msg.get("from", {}).get("address", "") or "").lower()
                if subject_contains and subject_contains.lower() not in subj:
                    continue
                if from_contains and from_contains.lower() not in from_addr:
                    continue
                seen_ids.add(mid)
                with httpx.Client(timeout=30) as c:
                    r2 = c.get(f"{_MAILTM_BASE}/messages/{mid}", headers=headers)
                    r2.raise_for_status()
                    full = r2.json()
                html = full.get("html")
                txt = full.get("text")
                if isinstance(html, list) and html:
                    text = html[0] or ""
                elif isinstance(html, str):
                    text = html
                elif isinstance(txt, list) and txt:
                    text = txt[0] or ""
                elif isinstance(txt, str):
                    text = txt
                else:
                    text = str(full)
                url = _extract_activation_url_from_text(text)
                if url:
                    return url
            time.sleep(self._poll_interval)
        raise TimeoutError(f"No activation email within {self._timeout}s for {email}")


# --- 1secMail (fallback if Mail.tm fails; may get 403 in some regions) ---
_1SEC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.1secmail.com/",
}
_1SEC_BASE = "https://www.1secmail.com/api/v1/"


class OneSecMailProvider:
    """Provider for temporary email via 1secMail API."""

    def __init__(self, poll_interval: float = 5.0, timeout: float = 120.0):
        """Initialize provider.

        Args:
            poll_interval: Seconds between inbox checks.
            timeout: Max seconds to wait for activation email.
        """
        self._poll_interval = poll_interval
        self._timeout = timeout
        self._domains: list[str] = []
        self._generated_in_session: set[str] = set()
        self._cache_path = os.environ.get(
            "AUTO_REGISTER_EMAIL_CACHE_PATH",
            os.path.join(tempfile.gettempdir(), "auto_register_used_emails.txt"),
        )

    def _load_used_cache(self) -> set[str]:
        try:
            if not os.path.exists(self._cache_path):
                return set()
            with open(self._cache_path, encoding="utf-8") as f:
                return {line.strip().lower() for line in f if line.strip()}
        except Exception:
            return set()

    def _append_used_cache(self, email: str) -> None:
        try:
            os.makedirs(os.path.dirname(self._cache_path), exist_ok=True)
            with open(self._cache_path, "a", encoding="utf-8") as f:
                f.write(email.lower().strip() + "\n")
        except Exception:
            # Cache is best-effort; ignore failures.
            pass

    def _request(self, action: str, params: Optional[dict[str, Any]] = None) -> Any:
        """Make API request with browser-like headers."""
        q = {"action": action}
        if params:
            q.update(params)
        with httpx.Client(headers=_1SEC_HEADERS, timeout=30) as client:
            r = client.get(_1SEC_BASE, params=q)
            r.raise_for_status()
            return r.json()

    def _get_domains(self) -> list[str]:
        """Fetch active domains (cached)."""
        if not self._domains:
            self._domains = self._request("getDomainList")
        return self._domains

    def generate_email(self) -> str:
        """Generate a random temporary email address.

        Note: 1secMail addresses are not reserved/created. To reduce collisions with
        previously used addresses (by anyone), we:
        - generate a stronger-unique login (uuid-based + random suffix)
        - avoid reuse within the same run
        - keep a best-effort local cache across runs
        - optionally reject addresses that already have inbox messages
        """
        domains = self._get_domains()
        used = self._load_used_cache()
        # Try multiple times to avoid collisions / previously used inboxes.
        for _ in range(30):
            # 16 hex + 4 random = 20 chars, still valid for 1secMail login.
            login = (uuid.uuid4().hex[:16] + "".join(random.choices(string.digits, k=4))).lower()
            domain = random.choice(domains)
            email = f"{login}@{domain}".lower()
            if email in self._generated_in_session or email in used:
                continue
            # If the inbox already has messages, it's likely a reused address; reject it.
            try:
                inbox = self._request("getMessages", params={"login": login, "domain": domain})
                if inbox:
                    continue
            except Exception:
                # If inbox check fails (network/403), still allow using the email.
                pass

            self._generated_in_session.add(email)
            self._append_used_cache(email)
            return email
        raise RuntimeError("1secMail: failed to generate a unique email after many attempts")

    def wait_for_activation_link(
        self,
        email: str,
        subject_contains: Optional[str] = None,
        from_contains: Optional[str] = None,
    ) -> str:
        """Poll inbox until activation email arrives, then extract first https link.

        Args:
            email: The temp email address.
            subject_contains: Optional filter for subject.
            from_contains: Optional filter for sender.

        Returns:
            First https URL found in the email body.

        Raises:
            TimeoutError: If no matching email within timeout.
            ValueError: If no https link found in email.
        """
        login, domain = email.split("@")
        start = time.time()
        seen_ids: set[int] = set()

        while (time.time() - start) < self._timeout:
            inbox = self._request(
                "getMessages",
                params={"login": login, "domain": domain},
            )

            for msg in inbox or []:
                msg_id = msg.get("id")
                if msg_id in seen_ids:
                    continue

                subj = (msg.get("subject") or "").lower()
                from_addr = (msg.get("from", "") or "").lower()
                if subject_contains and subject_contains.lower() not in subj:
                    continue
                if from_contains and from_contains.lower() not in from_addr:
                    continue

                seen_ids.add(msg_id)
                full = self._request(
                    "readMessage",
                    params={"login": login, "domain": domain, "id": msg_id},
                )
                url = self._extract_activation_url(full)
                if url:
                    return url

            time.sleep(self._poll_interval)

        raise TimeoutError(
            f"No activation email received within {self._timeout}s for {email}"
        )

    def _extract_activation_url(self, msg: dict[str, Any]) -> Optional[str]:
        """Extract first https activation/verification URL from email body."""
        text = (
            msg.get("htmlBody") or msg.get("textBody") or msg.get("body") or ""
        )
        return _extract_activation_url_from_text(text)


class CloudMailProvider:
    """Provider for self-hosted Cloud Mail API (mailcraft)."""

    def __init__(self, poll_interval: float = 5.0, timeout: float = 120.0):
        self._poll_interval = poll_interval
        self._timeout = timeout
        base_url = os.environ.get("CLOUDFLARE_TEMP_EMAIL_BASE_URL", "").strip()
        if not base_url:
            raise RuntimeError("CLOUDFLARE_TEMP_EMAIL_BASE_URL is required for cloudmail provider")
        self._base_url = base_url.rstrip("/")

        self._admin_email = os.environ.get("ADMIN_EMAIL", "").strip()
        if not self._admin_email:
            raise RuntimeError("ADMIN_EMAIL is required for cloudmail provider")

        self._admin_password = self._resolve_admin_password()
        if not self._admin_password:
            raise RuntimeError("ADMIN_PASSWORD or ADMIN_PASSWORDS is required for cloudmail provider")

        domain = os.environ.get("CLOUDFLARE_TEMP_EMAIL_DOMAIN", "").strip().lower()
        if domain:
            self._domain = domain
        elif "@" in self._admin_email:
            self._domain = self._admin_email.split("@", 1)[1].lower()
        else:
            raise RuntimeError("Cannot infer temp email domain, set CLOUDFLARE_TEMP_EMAIL_DOMAIN")

        self._token: Optional[str] = None

    def _resolve_admin_password(self) -> str:
        """Resolve admin password from ADMIN_PASSWORD or ADMIN_PASSWORDS."""
        plain = os.environ.get("ADMIN_PASSWORD", "").strip()
        if plain:
            return plain

        passwords = os.environ.get("ADMIN_PASSWORDS", "").strip()
        if not passwords:
            return ""

        try:
            parsed = json.loads(passwords)
            if isinstance(parsed, list) and parsed:
                return str(parsed[0]).strip()
        except Exception:
            pass

        cleaned = passwords.strip().strip("[]")
        if not cleaned:
            return ""
        first = cleaned.split(",", 1)[0].strip().strip('"').strip("'")
        return first

    def _request(
        self,
        path: str,
        payload: Optional[dict[str, Any]] = None,
        with_auth: bool = False,
    ) -> dict[str, Any]:
        """Send POST request to Cloud Mail API and validate response."""
        headers = {"Content-Type": "application/json"}
        if with_auth:
            headers["Authorization"] = self._get_token()

        with httpx.Client(timeout=30) as client:
            r = client.post(f"{self._base_url}{path}", json=payload or {}, headers=headers)
            r.raise_for_status()
            data = r.json()

        code = data.get("code")
        if code != 200:
            message = data.get("message") or "unknown error"
            raise RuntimeError(f"CloudMail API error {code}: {message}")
        return data

    def _get_token(self) -> str:
        """Get or refresh admin token."""
        if self._token:
            return self._token
        data = self._request(
            "/api/public/genToken",
            payload={"email": self._admin_email, "password": self._admin_password},
        )
        token = ((data.get("data") or {}).get("token") or "").strip()
        if not token:
            raise RuntimeError("CloudMail genToken returned empty token")
        self._token = token
        return token

    def _random_email(self) -> str:
        login = "qwen" + uuid.uuid4().hex[:10]
        return f"{login}@{self._domain}"

    def generate_email(self) -> str:
        """Create an inbox user via addUser and return the email address."""
        for _ in range(20):
            email = self._random_email().lower()
            try:
                self._request(
                    "/api/public/addUser",
                    payload={"list": [{"email": email}]},
                    with_auth=True,
                )
                return email
            except Exception:
                continue
        raise RuntimeError("CloudMail: failed to add user after multiple attempts")

    def wait_for_activation_link(
        self,
        email: str,
        subject_contains: Optional[str] = None,
        from_contains: Optional[str] = None,
    ) -> str:
        """Poll emailList endpoint and extract activation url."""
        start = time.time()
        seen_ids: set[int] = set()

        while (time.time() - start) < self._timeout:
            data = self._request(
                "/api/public/emailList",
                payload={
                    "toEmail": email,
                    "type": 0,
                    "isDel": 0,
                    "timeSort": "desc",
                    "num": 1,
                    "size": 20,
                },
                with_auth=True,
            )
            items = data.get("data") or []
            for msg in items:
                msg_id = msg.get("emailId")
                if msg_id in seen_ids:
                    continue

                subj = (msg.get("subject") or "").lower()
                from_email = (msg.get("sendEmail") or "").lower()
                from_name = (msg.get("sendName") or "").lower()
                if subject_contains and subject_contains.lower() not in subj:
                    continue
                if from_contains:
                    f = from_contains.lower()
                    if f not in from_email and f not in from_name:
                        continue

                seen_ids.add(msg_id)
                text = (
                    msg.get("content")
                    or msg.get("text")
                    or ""
                )
                url = _extract_activation_url_from_text(str(text))
                if url:
                    return url

            time.sleep(self._poll_interval)

        raise TimeoutError(f"No activation email received within {self._timeout}s for {email}")
