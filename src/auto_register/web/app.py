"""FastAPI web UI for registration flow control and live logs."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..integrations.qwen_portal import QwenPortalRunner


class StartRequest(BaseModel):
    """Run options from web UI."""

    headless: bool = False
    email_provider: Optional[str] = None
    loop_count: int = 1
    proxy_server: Optional[str] = None
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None
    proxy_bypass: Optional[str] = None


class RuntimeState:
    """In-memory run state for single-process web control."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.run_id = 0
        self.running = False
        self.success: Optional[bool] = None
        self.error: Optional[str] = None
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.logs: list[str] = []
        self.stop_requested = False

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def append_log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {message}"
        with self._lock:
            self.logs.append(line)
            if len(self.logs) > 2000:
                self.logs = self.logs[-2000:]

    def start_run(self) -> int:
        with self._lock:
            if self.running:
                raise RuntimeError("already running")
            self.run_id += 1
            self.running = True
            self.success = None
            self.error = None
            self.started_at = self._now_iso()
            self.finished_at = None
            self.logs = []
            self.stop_requested = False
            return self.run_id

    def finish_run(self, ok: bool, error: Optional[str]) -> None:
        with self._lock:
            self.running = False
            self.success = ok
            self.error = error
            self.finished_at = self._now_iso()

    def request_stop(self) -> bool:
        with self._lock:
            if not self.running:
                return False
            self.stop_requested = True
            return True

    def snapshot(self, tail: int = 300) -> dict:
        with self._lock:
            return {
                "run_id": self.run_id,
                "running": self.running,
                "success": self.success,
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "stop_requested": self.stop_requested,
                "logs": self.logs[-tail:],
            }


STATE = RuntimeState()


def _run_flow(run_id: int, req: StartRequest) -> None:
    """Background task wrapper for running QwenPortalRunner with loop support."""
    try:
        # 应用邮箱提供商
        if req.email_provider:
            os.environ["AUTO_REGISTER_EMAIL_PROVIDER"] = req.email_provider.strip()
            STATE.append_log(f"[Web] 已设置邮箱提供方: {req.email_provider.strip()}")

        # 应用代理配置
        if req.proxy_server:
            os.environ["QWEN_PLAYWRIGHT_PROXY"] = req.proxy_server.strip()
            STATE.append_log(f"[Web] 已设置代理服务器: {req.proxy_server.strip()}")
            
            if req.proxy_username:
                os.environ["QWEN_PLAYWRIGHT_PROXY_USERNAME"] = req.proxy_username.strip()
                STATE.append_log(f"[Web] 已设置代理用户名")
            
            if req.proxy_password:
                os.environ["QWEN_PLAYWRIGHT_PROXY_PASSWORD"] = req.proxy_password.strip()
                STATE.append_log(f"[Web] 已设置代理密码")
            
            if req.proxy_bypass:
                os.environ["QWEN_PLAYWRIGHT_PROXY_BYPASS"] = req.proxy_bypass.strip()
                STATE.append_log(f"[Web] 已设置代理绕过: {req.proxy_bypass.strip()}")

        # 循环执行
        loop_count = max(1, min(req.loop_count, 100))  # 限制在 1-100
        if loop_count > 1:
            STATE.append_log(f"[Web] 循环模式: {loop_count} 次")

        total_success = 0
        total_failed = 0

        for iteration in range(loop_count):
            # 在每次迭代开始前检查停止信号
            if STATE.stop_requested:
                STATE.append_log(f"[Web] ⚠ 已收到停止请求，中止循环执行")
                break

            iteration_num = iteration + 1
            STATE.append_log(f"\n[Web] ========== 第 {iteration_num}/{loop_count} 次运行 ==========")
            
            try:
                # 为每次循环启动一个全新的独立线程，防止 Playwright 状态/事件循环在连续调用时被重用而导致超时
                import threading
                
                result = {"ok": False, "error": None, "traceback": None}
                def _run_single_iteration():
                    try:
                        runner = QwenPortalRunner(
                            headless=req.headless, 
                            on_step=STATE.append_log,
                            check_stop=lambda: STATE.stop_requested
                        )
                        result["ok"] = runner.run()
                    except Exception as e:
                        result["error"] = e
                        import traceback
                        result["traceback"] = traceback.format_exc()
                
                t = threading.Thread(target=_run_single_iteration, daemon=True)
                t.start()
                t.join()  # 等待本次循环的独立线程完全结束
                
                if result["error"]:
                    raise Exception(f"{result['error']}\n{result['traceback']}")
                
                ok = result["ok"]
                
                if ok:
                    total_success += 1
                    STATE.append_log(f"[Web] ✓ 第 {iteration_num} 次运行成功")
                else:
                    total_failed += 1
                    STATE.append_log(f"[Web] ✗ 第 {iteration_num} 次运行未完成")

            except Exception as e:
                total_failed += 1
                STATE.append_log(f"[Web] ✗ 第 {iteration_num} 次运行异常: {e}")
                import traceback
                STATE.append_log(f"[Web] 详细: {traceback.format_exc()}")

            # 在循环间隔中频繁检查停止信号
            if iteration_num < loop_count:
                STATE.append_log(f"[Web] 等待 5 秒后开始下一次...")
                for i in range(5):
                    if STATE.stop_requested:
                        STATE.append_log(f"[Web] ⚠ 在循环间隔检测到停止请求，将立即中止")
                        break
                    import time
                    time.sleep(1)
                
                # 再次检查，确保停止请求被及时响应
                if STATE.stop_requested:
                    STATE.append_log(f"[Web] ⚠ 停止请求已生效，中止循环执行")
                    break

        # 最终结果
        STATE.append_log(f"\n[Web] ========== 循环结束 ==========")
        STATE.append_log(f"[Web] 成功: {total_success}, 失败: {total_failed}")
        
        if STATE.stop_requested:
            STATE.append_log(f"[Web] 任务已被用户中止")
        
        all_success = total_failed == 0 and total_success > 0
        STATE.finish_run(
            ok=all_success,
            error=None if all_success else f"成功 {total_success} 个，失败 {total_failed} 个"
        )

    except Exception as e:
        STATE.append_log(f"[Web] 运行异常: {e}")
        import traceback
        STATE.append_log(f"[Web] 详细: {traceback.format_exc()}")
        STATE.finish_run(ok=False, error=str(e))


def create_app() -> FastAPI:
    """Create and configure FastAPI app."""
    app = FastAPI(title="AutoRegister Web UI", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoRegister 控制台</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 16px;
        }
        .container {
            width: 100%;
            max-width: 900px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
            display: flex;
            flex-direction: column;
            height: 90vh;
            max-height: 800px;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 24px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .header h1 { font-size: 28px; margin-bottom: 8px; }
        .header p { font-size: 14px; opacity: 0.9; }
        .controls {
            padding: 20px 24px;
            border-bottom: 1px solid #e5e5e5;
            display: grid;
            grid-template-columns: 1fr auto auto auto;
            gap: 12px;
            align-items: center;
        }
        .control-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .control-group label { font-size: 14px; color: #333; }
        select {
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 14px;
            background: white;
            cursor: pointer;
        }
        input[type="checkbox"] { cursor: pointer; }
        button {
            padding: 10px 16px;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
        }
        .btn-primary {
            background: #667eea;
            color: white;
        }
        .btn-primary:hover:not(:disabled) { background: #5568d3; }
        .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
        .btn-danger {
            background: #f23645;
            color: white;
        }
        .btn-danger:hover:not(:disabled) { background: #d9202f; }
        .btn-danger:disabled { opacity: 0.6; cursor: not-allowed; }
        .status-bar {
            padding: 12px 24px;
            background: #f8f8f8;
            border-bottom: 1px solid #e5e5e5;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .status-icon {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
        }
        .status-icon.idle { background: #ddd; }
        .status-icon.running { background: #ffa500; animation: pulse 1s infinite; }
        .status-icon.success { background: #4caf50; }
        .status-icon.error { background: #f23645; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .status-text { flex: 1; color: #555; }
        .logs-container {
            flex: 1;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
        .logs {
            flex: 1;
            background: #1e1e1e;
            color: #e0e0e0;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.6;
            overflow-y: auto;
            padding: 16px;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .log-line { margin: 2px 0; }
        .log-info { color: #64b5f6; }
        .log-success { color: #4caf50; }
        .log-error { color: #f23645; }
        .log-warn { color: #ffa500; }
        @media (max-width: 768px) {
            .controls { grid-template-columns: 1fr; }
            .header h1 { font-size: 24px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 AutoRegister 控制台</h1>
            <p>一键自动注册、激活、认证 Qwen账户</p>
        </div>

        <div class="controls">
            <div class="control-group">
                <label for="provider">邮箱:</label>
                <select id="provider">
                    <option value="cloudflare">Cloudflare</option>
                    <option value="mailtm">MailTM</option>
                    <option value="1secmail">1SecMail</option>
                </select>
            </div>
            <div class="control-group">
                <label for="loopCount">循环次数:</label>
                <input type="number" id="loopCount" min="1" max="100" value="1" style="width: 60px; padding: 6px; border: 1px solid #ddd; border-radius: 6px;">
            </div>
            <div class="control-group">
                <input id="headless" type="checkbox">
                <label for="headless">无头模式</label>
            </div>
            <button id="btnConfigProxy" class="btn-primary">代理配置</button>
            <button id="btnStart" class="btn-primary">启动</button>
            <button id="btnStop" class="btn-danger" disabled>停止</button>
        </div>

        <div id="proxyModal" style="display:none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 1000; display: flex; justify-content: center; align-items: center;">
            <div style="background: white; padding: 24px; border-radius: 12px; width: 90%; max-width: 500px; max-height: 80vh; overflow-y: auto; box-shadow: 0 10px 40px rgba(0,0,0,0.3);">
                <h2 style="margin: 0 0 16px 0; font-size: 20px;">代理配置</h2>
                <div style="margin-bottom: 16px;">
                    <label style="display: block; font-size: 14px; margin-bottom: 6px; color: #333;">代理服务器 (http://proxy:port)</label>
                    <input type="text" id="proxyServer" placeholder="例: http://127.0.0.1:8080" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;">
                </div>
                <div style="margin-bottom: 16px;">
                    <label style="display: block; font-size: 14px; margin-bottom: 6px; color: #333;">代理用户名</label>
                    <input type="text" id="proxyUsername" placeholder="可选" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;">
                </div>
                <div style="margin-bottom: 16px;">
                    <label style="display: block; font-size: 14px; margin-bottom: 6px; color: #333;">代理密码</label>
                    <input type="password" id="proxyPassword" placeholder="可选" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;">
                </div>
                <div style="margin-bottom: 16px;">
                    <label style="display: block; font-size: 14px; margin-bottom: 6px; color: #333;">绕过代理的域名 (逗号分隔)</label>
                    <input type="text" id="proxyBypass" placeholder="例: localhost,127.0.0.1,.local" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;">
                </div>
                <div style="display: flex; gap: 10px;">
                    <button id="btnProxySave" class="btn-primary" style="flex: 1;">保存</button>
                    <button id="btnProxyCancel" class="btn-primary" style="flex: 1; background: #999;">取消</button>
                    <button id="btnProxyClear" class="btn-danger" style="flex: 1;">清除</button>
                </div>
            </div>
        </div>

        <div class="status-bar">
            <span class="status-icon idle" id="statusIcon"></span>
            <span class="status-text" id="statusText">待机</span>
        </div>

        <div class="logs-container">
            <div class="logs" id="logs">等待启动...</div>
        </div>
    </div>

    <script>
        // 等待 DOM 完全加载
        function initUI() {
            const btnStart = document.getElementById('btnStart');
            const btnStop = document.getElementById('btnStop');
            const btnConfigProxy = document.getElementById('btnConfigProxy');
            const statusIcon = document.getElementById('statusIcon');
            const statusText = document.getElementById('statusText');
            const logsDiv = document.getElementById('logs');
            const provider = document.getElementById('provider');
            const headless = document.getElementById('headless');
            const loopCount = document.getElementById('loopCount');

            // 代理配置 UI - 确保都存在
            const proxyModal = document.getElementById('proxyModal');
            const proxyServer = document.getElementById('proxyServer');
            const proxyUsername = document.getElementById('proxyUsername');
            const proxyPassword = document.getElementById('proxyPassword');
            const proxyBypass = document.getElementById('proxyBypass');
            const btnProxySave = document.getElementById('btnProxySave');
            const btnProxyCancel = document.getElementById('btnProxyCancel');
            const btnProxyClear = document.getElementById('btnProxyClear');

            let isRunning = false;
            let currentRunId = 0;

            function hasCoreElements() {
                const hasCore = !!(btnStart && btnStop && statusIcon && statusText && logsDiv && provider && headless && loopCount);
                const hasProxy = !!(proxyModal && proxyServer && proxyUsername && proxyPassword && proxyBypass && btnProxySave && btnProxyCancel && btnProxyClear);
                if (!hasCore || !hasProxy) {
                    console.error('缺少 DOM 元素：', { hasCore, hasProxy });
                }
                return hasCore && hasProxy;
            }

            if (!hasCoreElements()) {
                console.error('Web UI 初始化失败：缺少关键 DOM 元素');
                return;
            }

            // 从 localStorage 加载代理配置
            function loadProxyConfig() {
                try {
                    const saved = localStorage.getItem('proxyConfig');
                    if (saved) {
                        const config = JSON.parse(saved);
                        proxyServer.value = config.server || '';
                        proxyUsername.value = config.username || '';
                        proxyPassword.value = config.password || '';
                        proxyBypass.value = config.bypass || '';
                    }
                } catch (e) {
                    console.error('Failed to load proxy config:', e);
                }
            }

            // 保存代理配置
            function saveProxyConfig() {
                const config = {
                    server: proxyServer.value.trim(),
                    username: proxyUsername.value.trim(),
                    password: proxyPassword.value.trim(),
                    bypass: proxyBypass.value.trim(),
                };
                localStorage.setItem('proxyConfig', JSON.stringify(config));
            }

            // 代理配置按钮事件 - 修复并简化绑定方式
            btnConfigProxy.addEventListener('click', (e) => {
                e.preventDefault();
                console.log('打开代理配置对话框');
                loadProxyConfig();
                proxyModal.style.display = 'flex';
            });

            btnProxySave.addEventListener('click', (e) => {
                e.preventDefault();
                console.log('保存代理配置');
                saveProxyConfig();
                proxyModal.style.display = 'none';
            });

            btnProxyCancel.addEventListener('click', (e) => {
                e.preventDefault();
                console.log('取消代理配置');
                proxyModal.style.display = 'none';
            });

            btnProxyClear.addEventListener('click', (e) => {
                e.preventDefault();
                if (confirm('确定要清除所有代理配置吗？')) {
                    console.log('清除代理配置');
                    proxyServer.value = '';
                    proxyUsername.value = '';
                    proxyPassword.value = '';
                    proxyBypass.value = '';
                    localStorage.removeItem('proxyConfig');
                    proxyModal.style.display = 'none';
                }
            });

            // 点击模态框外关闭
            proxyModal.addEventListener('click', (e) => {
                if (e.target === proxyModal) {
                    console.log('点击对话框外，关闭');
                    proxyModal.style.display = 'none';
                }
            });

            function setStatus(text, state) {
                statusText.textContent = text;
                statusIcon.className = 'status-icon ' + state;
            }

            function appendLog(message, type = 'info') {
                if (logsDiv.textContent === '等待启动...') {
                    logsDiv.textContent = '';
                }
                const line = document.createElement('div');
                line.className = 'log-line log-' + type;
                const stamp = new Date().toLocaleTimeString('zh-CN');
                line.textContent = `[${stamp}] ${message}`;
                logsDiv.appendChild(line);
                logsDiv.scrollTop = logsDiv.scrollHeight;
            }

            function clearLogs() {
                logsDiv.textContent = '等待启动...';
            }

            async function updateStatus() {
                try {
                    const res = await fetch('/api/status');
                    const data = await res.json();
                    
                    if (data.running) {
                        setStatus(`运行中 (ID: ${data.run_id})`, 'running');
                        isRunning = true;
                        btnStart.disabled = true;
                        btnStop.disabled = false;
                        btnConfigProxy.disabled = true;
                    } else {
                        btnStart.disabled = false;
                        btnStop.disabled = true;
                        btnConfigProxy.disabled = false;
                        isRunning = false;
                        
                        if (data.success === true) {
                            setStatus(`✓ 已完成 (ID: ${data.run_id})`, 'success');
                        } else if (data.success === false) {
                            setStatus(`✗ 失败: ${data.error || '未知错误'}`, 'error');
                        } else {
                            setStatus('待机', 'idle');
                        }
                    }

                    // 更新日志
                    const logs = data.logs || [];
                    if (logs.length > 0) {
                        logsDiv.innerHTML = '';
                        logs.forEach(logLine => {
                            const line = document.createElement('div');
                            line.className = 'log-line';
                            // 根据内容类型着色
                            if (logLine.includes('成功') || logLine.includes('✓')) {
                                line.classList.add('log-success');
                            } else if (logLine.includes('失败') || logLine.includes('错误') || logLine.includes('✗') || logLine.includes('异常')) {
                                line.classList.add('log-error');
                            } else if (logLine.includes('警告') || logLine.includes('停止')) {
                                line.classList.add('log-warn');
                            }
                            line.textContent = logLine;
                            logsDiv.appendChild(line);
                        });
                        logsDiv.scrollTop = logsDiv.scrollHeight;
                    } else if (!data.running) {
                        logsDiv.textContent = '等待启动...';
                    }
                } catch (e) {
                    console.error('获取状态失败:', e);
                    setStatus(`状态获取失败: ${e.message}`, 'error');
                }
            }

            btnStart.addEventListener('click', async () => {
                console.log('点击启动按钮');
                clearLogs();
                appendLog('正在启动任务...', 'info');
                setStatus('启动中...', 'running');
                btnStart.disabled = true;
                btnStop.disabled = true;
                btnConfigProxy.disabled = true;

                // 获取代理配置
                let proxyConfig = null;
                try {
                    proxyConfig = JSON.parse(localStorage.getItem('proxyConfig') || '{}');
                } catch (e) {
                    proxyConfig = {};
                }

                try {
                    const res = await fetch('/api/start', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            headless: headless.checked,
                            email_provider: provider.value || null,
                            loop_count: parseInt(loopCount.value) || 1,
                            proxy_server: proxyConfig.server || null,
                            proxy_username: proxyConfig.username || null,
                            proxy_password: proxyConfig.password || null,
                            proxy_bypass: proxyConfig.bypass || null,
                        }),
                    });

                    if (res.ok) {
                        const data = await res.json();
                        currentRunId = data.run_id;
                        appendLog(`任务已启动 (ID: ${data.run_id})`, 'success');
                        isRunning = true;
                        btnStop.disabled = false;
                    } else {
                        const error = await res.text();
                        appendLog(`启动失败: ${error}`, 'error');
                        setStatus('启动失败', 'error');
                        btnStart.disabled = false;
                        btnConfigProxy.disabled = false;
                    }
                } catch (e) {
                    console.error('启动异常:', e);
                    appendLog(`启动异常: ${e.message}`, 'error');
                    setStatus('启动异常', 'error');
                    btnStart.disabled = false;
                    btnConfigProxy.disabled = false;
                }
            });

            btnStop.addEventListener('click', async () => {
                console.log('点击停止按钮');
                appendLog('正在停止任务...', 'warn');
                btnStop.disabled = true;

                try {
                    const res = await fetch('/api/stop', { method: 'POST' });
                    if (res.ok) {
                        const data = await res.json();
                        appendLog('停止信号已发送，任务将在当前步骤完成后停止', 'warn');
                        console.log('停止响应:', data);
                    } else {
                        appendLog(`停止请求失败: HTTP ${res.status}`, 'error');
                        console.error('停止失败，状态码:', res.status);
                    }
                } catch (e) {
                    console.error('停止异常:', e);
                    appendLog(`停止异常: ${e.message}`, 'error');
                }
            });

            window.addEventListener('error', (event) => {
                console.error('前端脚本异常:', event);
                if (statusText) {
                    statusText.textContent = `前端脚本异常: ${event.message}`;
                    statusIcon.className = 'status-icon error';
                }
            });

            // 定期更新状态和日志（1秒间隔）
            setInterval(updateStatus, 1000);
            updateStatus();
        }

        // 文档加载完成后初始化
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initUI);
        } else {
            initUI();
        }
    </script>
</body>
</html>"""

    @app.get("/api/status")
    def status() -> dict:
        return STATE.snapshot()

    @app.post("/api/start")
    def start(req: StartRequest) -> dict:
        try:
            run_id = STATE.start_run()
        except RuntimeError:
            raise HTTPException(status_code=409, detail="已有任务在运行")

        STATE.append_log(f"[Web] run_id={run_id} 开始执行")
        t = threading.Thread(target=_run_flow, args=(run_id, req), daemon=True)
        t.start()
        return {"ok": True, "run_id": run_id}

    @app.get("/api/start")
    def start_get(headless: int = 0, email_provider: str = "") -> dict:
        req = StartRequest(headless=bool(headless), email_provider=(email_provider or None))
        try:
            run_id = STATE.start_run()
        except RuntimeError:
            raise HTTPException(status_code=409, detail="已有任务在运行")

        STATE.append_log(f"[Web] run_id={run_id} 开始执行")
        t = threading.Thread(target=_run_flow, args=(run_id, req), daemon=True)
        t.start()
        return {"ok": True, "run_id": run_id}

    @app.post("/api/stop")
    def stop() -> dict:
        changed = STATE.request_stop()
        if changed:
            STATE.append_log("[Web] 已请求停止。当前版本会在本轮流程结束后生效。")
        return {"ok": True, "stop_requested": changed}

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    return app


def run_web(host: str = "0.0.0.0", port: int = 18080) -> int:
    """Run web UI server."""
    import uvicorn

    app = create_app()
    uvicorn.run(app, host=host, port=port)
    return 0
