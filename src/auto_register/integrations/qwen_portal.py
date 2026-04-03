"""Qwen registration + activation runner with remote auth-link handoff."""

import os
import string
from dataclasses import dataclass
from typing import Callable, Optional

from playwright.sync_api import Page, sync_playwright

from .cli_proxy_management_client import get_qwen_auth_url, list_auth_files, poll_auth_status
from ..providers.one_sec_mail_provider import get_email_provider
from ..providers.username_provider import UsernameProvider


@dataclass
class QwenCredentials:
    """Credentials for a single Qwen registration."""

    username: str
    email: str
    password: str


def _generate_password(length: int = 14) -> str:
    """生成符合 Qwen 要求的密码：大小写字母+数字，≥8位。使用14位避免过长导致表单异常。"""
    import random
    # 强制包含至少各一个，满足 Qwen 要求
    pwd = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
    ]
    pwd += list(random.choices(string.ascii_letters + string.digits, k=length - 3))
    random.shuffle(pwd)
    return "".join(pwd)


class QwenPortalRunner:
    """Run simplified flow: register -> activate -> remote auth-link handoff."""

    REGISTER_URL = "https://chat.qwen.ai/auth?mode=register"

    PROXY_LINK_AUTH_MODES = (
        "cli-proxy-api-remote",
        "cli_proxy_api_remote",
        "proxy-link",
        "proxy_link",
        "management-api",
        "management_api",
    )

    def __init__(
        self,
        headless: bool = False,
        on_step: Optional[Callable[[str], None]] = None,
        check_stop: Optional[Callable[[], bool]] = None,
    ):
        self._headless = headless
        self._on_step = on_step or (lambda _: None)
        self._check_stop = check_stop or (lambda: False)
        self._latest_creds: Optional[QwenCredentials] = None

    def _log(self, msg: str) -> None:
        self._on_step(msg)

    def _current_url(self, page: Page) -> str:
        """Return current page URL for diagnostics."""
        try:
            return page.url or "<empty-url>"
        except Exception:
            return "<unknown-url>"

    def _auth_mode(self) -> str:
        return (
            os.environ.get("QWEN_AUTH_MODE")
            or os.environ.get("AUTO_REGISTER_AUTH_MODE")
            or "cli-proxy-api-remote"
        ).strip().lower()

    def _resolve_browser_proxy(self) -> Optional[dict]:
        """Resolve Playwright proxy from env for browser automation."""
        proxy_server = (
            os.environ.get("QWEN_PLAYWRIGHT_PROXY")
            or os.environ.get("PLAYWRIGHT_PROXY")
            or os.environ.get("HTTPS_PROXY")
            or os.environ.get("HTTP_PROXY")
            or ""
        ).strip()
        if not proxy_server:
            return None

        proxy: dict = {"server": proxy_server}

        bypass = (
            os.environ.get("QWEN_PLAYWRIGHT_PROXY_BYPASS")
            or os.environ.get("NO_PROXY")
            or ""
        ).strip()
        if bypass:
            proxy["bypass"] = bypass

        username = (os.environ.get("QWEN_PLAYWRIGHT_PROXY_USERNAME") or "").strip()
        password = (os.environ.get("QWEN_PLAYWRIGHT_PROXY_PASSWORD") or "").strip()
        if username:
            proxy["username"] = username
        if password:
            proxy["password"] = password

        return proxy

    def _browser_launch_options(self) -> dict:
        """Build Chromium launch options with optional proxy support."""
        options = {"headless": self._headless}
        proxy = self._resolve_browser_proxy()
        if proxy:
            options["proxy"] = proxy
            server = str(proxy.get("server") or "")
            self._log(f"[Browser] 已启用代理: {server}")
            bypass = str(proxy.get("bypass") or "").strip()
            if bypass:
                self._log(f"[Browser] 代理绕过列表: {bypass}")
        else:
            self._log("[Browser] 未配置 Playwright 代理，直连访问")
        return options

    def run(self) -> bool:
        """Execute full flow. Returns True on success."""
        # 检查停止信号
        if self._check_stop():
            self._log("[Portal] 任务已被停止")
            return False
            
        mail_provider = get_email_provider(poll_interval=5.0, timeout=120.0)
        creds = QwenCredentials(
            username=UsernameProvider().get(),
            email=mail_provider.generate_email(),
            password=_generate_password(),
        )
        self._latest_creds = creds
        self._log(f"1. 临时邮箱: {creds.email}")
        self._log(f"2. 随机密码已生成")

        with sync_playwright() as p:
            browser = p.chromium.launch(**self._browser_launch_options())
            context = browser.new_context()
            page = context.new_page()

            try:
                # 在流程中多点检查停止信号
                if self._check_stop():
                    self._log("[Portal] 在打开浏览器后收到停止请求，放弃此次注册")
                    return False
                    
                self._do_register(page, creds)
                self._log("4. 已提交注册，等待激活邮件...")
                
                if self._check_stop():
                    self._log("[Portal] 在等待邮件前收到停止请求，放弃此次注册")
                    return False
                    
                activation_url = mail_provider.wait_for_activation_link(creds.email)
                self._log("5. 收到激活邮件")
                
                if self._check_stop():
                    self._log("[Portal] 在激活前收到停止请求，放弃此次注册")
                    return False
                    
                page.goto(activation_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)
                self._log("6. 已打开激活链接")
                mode = self._auth_mode()
                self._log(f"7. 当前认证模式: {mode}")
                if mode not in self.PROXY_LINK_AUTH_MODES:
                    self._log(
                        f"7. 模式 {mode} 不在远程链接模式列表中，按当前项目默认强制切换到 cli-proxy-api-remote"
                    )

                if self._check_stop():
                    self._log("[Portal] 在启动认证前收到停止请求，放弃此次注册")
                    return False
                    
                self._log("8. 启动远程管理 API 登录链接流程...")
                ok = self._run_remote_proxy_link_auth(page, creds)
                if ok:
                    self._log("9. 远程认证流程完成（由 CLI Proxy API 侧维护认证文件）")
                    return True
                self._log("9. 远程认证流程失败")
                return False
            except Exception as e:
                self._log(f"错误: {e}")
                raise
            finally:
                browser.close()

    def _run_remote_proxy_link_auth(self, page: Page, creds: QwenCredentials) -> bool:
        """Use CLI Proxy management API to get auth URL and complete remote flow."""
        base_url = (os.environ.get("CLI_PROXY_API_BASE_URL") or "").strip()
        management_key = (os.environ.get("CLI_PROXY_API_KEY") or "").strip()
        if not base_url or not management_key:
            self._log("[ProxyLink] 缺少 CLI_PROXY_API_BASE_URL 或 CLI_PROXY_API_KEY")
            return False

        try:
            auth_url, state = get_qwen_auth_url(base_url=base_url, management_key=management_key)
        except Exception as e:
            self._log(f"[ProxyLink] 获取登录链接失败: {e}")
            return False

        self._log(f"[ProxyLink] 获取登录链接成功，state={state}")
        page.goto(auth_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)
        self._log(f"[ProxyLink] 已打开登录链接，当前页面: {self._current_url(page)}")

        self._log(f"[ProxyLink] 使用本次注册凭据执行登录: {creds.email}")
        self._complete_two_stage_auth(page, creds)

        def on_wait() -> None:
            self._log("[ProxyLink] 等待远程认证完成...")

        ok, err = poll_auth_status(
            base_url=base_url,
            management_key=management_key,
            state=state,
            poll_interval=2.0,
            timeout_seconds=300.0,
            on_wait=on_wait,
        )
        if not ok:
            self._log(f"[ProxyLink] 认证状态失败: {err}")
            return False

        # 仅用于观测，不做本地写入。
        try:
            files = list_auth_files(base_url=base_url, management_key=management_key)
            qwen_count = len([f for f in files if str((f or {}).get("provider") or "").lower() == "qwen"])
            self._log(f"[ProxyLink] 远端可见 qwen 认证文件数: {qwen_count}")
        except Exception as e:
            self._log(f"[ProxyLink] 读取远端认证文件列表失败（可忽略）: {e}")

        return True

    def _complete_two_stage_auth(self, page: Page, creds: QwenCredentials) -> None:
        """Handle common two-stage flow: login form -> confirmation page."""
        login_submitted = False
        confirm_clicked = False
        max_rounds = 8

        for round_idx in range(1, max_rounds + 1):
            self._log(
                f"[ProxyLink][Round {round_idx}/{max_rounds}] 检查登录与确认页面，URL={self._current_url(page)}"
            )
            if not login_submitted:
                login_submitted = self._try_login_on_auth_page(page, creds, round_idx)
            else:
                self._log(f"[ProxyLink][Round {round_idx}] 登录步骤已完成，跳过重复登录")

            if self._auto_click_auth_action(page, round_idx):
                confirm_clicked = True
                break

            self._log(f"[ProxyLink][Round {round_idx}] 未点击到确认按钮，等待页面更新后重试")

            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(1500)

        if login_submitted:
            self._log("[ProxyLink] 第一阶段登录表单已提交")
        else:
            self._log("[ProxyLink] 未检测到登录表单，可能已登录或页面已跳过该步骤")

        if confirm_clicked:
            self._log("[ProxyLink] 第二阶段确认按钮已点击")
        else:
            self._log("[ProxyLink] 未检测到确认按钮，继续轮询远程状态")

    def _try_login_on_auth_page(self, page: Page, creds: QwenCredentials, round_idx: int) -> bool:
        """Try login for auth-link page and return whether submit happened."""
        try:
            email_input = page.locator(
                'input[type="email"], input[name="email"], input[placeholder*="邮箱"], input[placeholder*="电子邮箱"]'
            ).first
            if email_input.count() <= 0 or not email_input.is_visible():
                self._log(f"[ProxyLink][Round {round_idx}] 未检测到可见邮箱输入框")
                return False

            self._log(f"[ProxyLink][Round {round_idx}] 检测到邮箱输入框，开始填入注册邮箱")
            email_input.fill(creds.email)

            pw_input = page.locator(
                'input[type="password"], input[name="password"], input[placeholder*="密码"]'
            ).first
            if pw_input.count() > 0 and pw_input.is_visible():
                pw_input.fill(creds.password)
                self._log(f"[ProxyLink][Round {round_idx}] 已填入密码（长度={len(creds.password)}）")
            else:
                self._log(f"[ProxyLink][Round {round_idx}] 未检测到可见密码输入框")

            submit = page.locator(
                'button[type="submit"], button:has-text("登录"), button:has-text("Login"), button:has-text("继续"), button:has-text("Continue")'
            ).first
            if submit.count() > 0 and submit.is_visible():
                submit.click()
                page.wait_for_timeout(2000)
                self._log(f"[ProxyLink][Round {round_idx}] 已提交登录表单")
                return True

            self._log(f"[ProxyLink][Round {round_idx}] 未找到可点击的登录按钮")
        except Exception:
            # Best-effort only; ignore form mismatch.
            self._log(f"[ProxyLink][Round {round_idx}] 登录步骤异常，继续重试")
            return False

        return False

    def _do_register(self, page: Page, creds: QwenCredentials) -> None:
        """Fill and submit registration form."""
        self._log("3. 打开注册页并填写表单")
        page.goto(self.REGISTER_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        # 用户名（第一个文本输入框，或 placeholder 含「用户」）
        try:
            username_input = page.locator(
                'input[placeholder*="用户"], input[placeholder*="username"], input[name="username"], input[type="text"]'
            ).first
            username_input.wait_for(state="visible", timeout=5000)
            username_input.fill(creds.username)
        except Exception:
            pass

        # 邮箱
        email_input = page.locator('input[type="email"], input[name="email"], input[placeholder*="邮箱"]').first
        email_input.wait_for(state="visible", timeout=10000)
        email_input.fill(creds.email)

        # 密码与确认密码
        pw_inputs = page.locator('input[type="password"]')
        count = pw_inputs.count()
        if count >= 1:
            pw_inputs.nth(0).fill(creds.password)
        if count >= 2:
            pw_inputs.nth(1).fill(creds.password)

        # 勾选「我同意用户条款和隐私协议」
        try:
            # 优先：通过 label 文字定位
            label = page.locator('label').filter(has_text="我同意").first
            if label.count() > 0:
                label.click()
            else:
                # 备选：直接勾选表单中唯一的 checkbox
                cb = page.locator('input[type="checkbox"]').first
                if cb.count() > 0:
                    cb.check()
        except Exception:
            pass

        page.wait_for_timeout(800)

        # 等待提交按钮可用（填完表单并勾选协议后会解除 disabled / .disabled 类）
        submit = page.locator('button[type="submit"], button:has-text("注册"), button:has-text("Register")').first
        submit.wait_for(state="visible", timeout=5000)
        page.wait_for_function(
            """() => {
                const btn = document.querySelector('button[type=submit]');
                if (!btn) return false;
                if (btn.disabled) return false;
                if (btn.classList.contains('disabled')) return false;
                return true;
            }""",
            timeout=10000,
        )
        submit.click()
        page.wait_for_timeout(3000)

    def _auto_click_auth_action(self, page: Page, round_idx: int) -> bool:
        """Best-effort click for common approval/confirm buttons on auth page."""
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(1000)

        selectors = [
            'button:has-text("同意")',
            'button:has-text("授权")',
            'button:has-text("允许")',
            'button:has-text("确认")',
            'button:has-text("Approve")',
            'button:has-text("Authorize")',
            'button:has-text("Allow")',
            'button:has-text("Continue")',
            'a:has-text("同意")',
            'a:has-text("授权")',
            'a:has-text("允许")',
            '[role="button"]:has-text("同意")',
            '[role="button"]:has-text("授权")',
            '[data-testid="approve"]',
            'button[type="submit"]',
            'input[type="submit"]',
            'div[class*="primary"]:has-text("同意")',
            'div[class*="submit"]:has-text("同意")',
        ]
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                btn.wait_for(state="visible", timeout=3000)
                btn.click()
                self._log(f"[ProxyLink][Round {round_idx}] 已自动点击授权按钮，selector={sel}")
                page.wait_for_timeout(2000)
                return True
            except Exception:
                continue

        clicked = page.evaluate("""() => {
            const texts = ['同意', '授权', '允许', 'Approve', 'Authorize', 'Allow', '确认'];
            const nodes = document.querySelectorAll('button, a, [role="button"], input[type="submit"]');
            for (const el of nodes) {
                const t = (el.textContent || '').trim();
                if (texts.some(x => t.includes(x))) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        if clicked:
            self._log(f"[ProxyLink][Round {round_idx}] 已自动点击授权按钮（JS 文本查找）")
            page.wait_for_timeout(2000)
            return True

        self._log(f"[ProxyLink][Round {round_idx}] 当前页面未匹配到确认/授权按钮")
        return False
