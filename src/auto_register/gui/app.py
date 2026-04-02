"""Main GUI application for Qwen Token acquisition."""

import os
import threading
from typing import Optional

import customtkinter as ctk

from ..integrations.qwen_portal import QwenPortalRunner
from .log_panel import LogPanel


def run_gui() -> int:
    """Launch the GUI. Returns exit code."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()
    return 0


class App(ctk.CTk):
    """Main window with flow controls and log panel."""

    def __init__(self):
        super().__init__()
        self.title("AutoRegister - Qwen Token 自动获取")
        self.geometry("700x500")
        self.minsize(500, 400)

        self._running = False
        self._build_ui()

    def _build_ui(self) -> None:
        # Header
        header = ctk.CTkLabel(
            self,
            text="Qwen Token 自动获取",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        header.pack(pady=(15, 5))

        desc = ctk.CTkLabel(
            self,
            text="注册 → 激活 → 远程登录链接认证（CLI Proxy API）",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        desc.pack(pady=(0, 15))

        # Controls
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=20, pady=(0, 10))

        # Email provider select
        provider_frame = ctk.CTkFrame(ctrl, fg_color="transparent")
        provider_frame.pack(side="left", padx=(0, 15))

        provider_label = ctk.CTkLabel(provider_frame, text="临时邮箱")
        provider_label.pack(side="left", padx=(0, 8))

        # Env: AUTO_REGISTER_EMAIL_PROVIDER = "mailtm" | "1secmail" | "cloudflare"
        default_provider = os.environ.get("AUTO_REGISTER_EMAIL_PROVIDER", "mailtm").lower().strip() or "mailtm"
        if default_provider not in ("mailtm", "1secmail", "cloudflare"):
            default_provider = "mailtm"
        self._email_provider_var = ctk.StringVar(value=default_provider)
        provider_menu = ctk.CTkOptionMenu(
            provider_frame,
            values=["mailtm", "1secmail", "cloudflare"],
            variable=self._email_provider_var,
            width=120,
        )
        provider_menu.pack(side="left")

        self._headless_var = ctk.BooleanVar(value=False)
        headless_cb = ctk.CTkCheckBox(
            ctrl,
            text="无头模式",
            variable=self._headless_var,
        )
        headless_cb.pack(side="left", padx=(0, 15))

        self._start_btn = ctk.CTkButton(
            ctrl,
            text="开始",
            command=self._on_start,
            width=100,
        )
        self._start_btn.pack(side="left", padx=(0, 8))

        self._stop_btn = ctk.CTkButton(
            ctrl,
            text="停止",
            command=self._on_stop,
            state="disabled",
            width=100,
            fg_color="gray",
        )
        self._stop_btn.pack(side="left")

        # Theme toggle
        self._theme_btn = ctk.CTkButton(
            ctrl,
            text="浅色",
            command=self._toggle_theme,
            width=60,
        )
        self._theme_btn.pack(side="right")

        # Log panel
        log_frame = ctk.CTkFrame(self, fg_color="transparent")
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        log_label = ctk.CTkLabel(log_frame, text="日志", font=ctk.CTkFont(weight="bold"))
        log_label.pack(anchor="w")

        self._log = LogPanel(
            log_frame,
            height=250,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self._log.pack(fill="both", expand=True, pady=(5, 0))

        clear_btn = ctk.CTkButton(
            log_frame,
            text="清空",
            command=self._log.clear,
            width=60,
        )
        clear_btn.pack(anchor="e", pady=(5, 0))

    def _toggle_theme(self) -> None:
        current = ctk.get_appearance_mode()
        if current == "Dark":
            ctk.set_appearance_mode("Light")
            self._theme_btn.configure(text="深色")
        else:
            ctk.set_appearance_mode("Dark")
            self._theme_btn.configure(text="浅色")

    def _on_start(self) -> None:
        if self._running:
            return
        self._running = True
        # Apply provider selection to current process (used by providers.get_email_provider).
        os.environ["AUTO_REGISTER_EMAIL_PROVIDER"] = (self._email_provider_var.get() or "mailtm").strip()
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._log.clear()
        self._log.append("开始执行 Qwen Token 获取流程...")
        thread = threading.Thread(target=self._run_flow, daemon=True)
        thread.start()

    def _on_stop(self) -> None:
        self._running = False
        self._log.append("用户请求停止（当前步骤完成后生效）")

    def _run_flow(self) -> None:
        def on_step(msg: str) -> None:
            self.after(0, lambda: self._log.append(msg))

        try:
            runner = QwenPortalRunner(
                headless=self._headless_var.get(),
                on_step=on_step,
            )
            ok = runner.run()
            self.after(0, lambda: self._on_done(ok))
        except Exception as e:
            err_msg = str(e)
            self.after(0, lambda msg=err_msg: self._on_done(False, msg))

    def _on_done(self, success: bool, error: Optional[str] = None) -> None:
        self._running = False
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        if error:
            self._log.append(f"错误: {error}")
        if success:
            self._log.append("")
            self._log.append("✅ 完成！注册激活流程已完成。")
        else:
            self._log.append("")
            self._log.append("❌ 流程未完成，请检查上方日志。")
