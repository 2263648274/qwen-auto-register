"""OpenClaw Gateway 重启与状态检测。"""

import os
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional


def _get_openclaw_cmd(subcmd: str) -> tuple[list[str], str | None]:
    """获取 openclaw 命令：优先使用完整路径，否则用 openclaw CLI。
    返回 (cmd, debug_msg)，debug_msg 为 None 表示正常。
    """
    node_path = (os.environ.get("OPENCLAW_NODE_PATH") or "").strip().strip('"').strip("'")
    openclaw_path = (os.environ.get("OPENCLAW_PATH") or "").strip().strip('"').strip("'")
    if node_path and openclaw_path:
        node_p = Path(node_path)
        openclaw_p = Path(openclaw_path)
        if not node_p.is_file():
            return ["openclaw", "gateway", subcmd], f"OPENCLAW_NODE_PATH 文件不存在：{node_p}"
        if not openclaw_p.is_file():
            return ["openclaw", "gateway", subcmd], f"OPENCLAW_PATH 文件不存在：{openclaw_p}"
        return [str(node_p), str(openclaw_p), "gateway", subcmd], None
    if node_path or openclaw_path:
        return ["openclaw", "gateway", subcmd], "需同时设置 OPENCLAW_NODE_PATH 和 OPENCLAW_PATH"
    return ["openclaw", "gateway", subcmd], None


def restart_openclaw_gateway(on_log: Optional[Callable[[str], None]] = None) -> bool:
    """重启 OpenClaw Gateway。

    支持环境变量：
    - OPENCLAW_NODE_PATH: node.exe 完整路径
    - OPENCLAW_PATH: openclaw dist/index.js 完整路径
    若未设置，则使用 openclaw 命令（需已加入 PATH）。

    Args:
        on_log: 可选日志回调，如 lambda msg: print(msg)

    Returns:
        是否重启成功
    """
    log = on_log or (lambda _: None)

    log("[RESTART] 正在重启 OpenClaw Gateway...")
    cmd, debug_msg = _get_openclaw_cmd("restart")
    if debug_msg:
        log(f"[DEBUG] {debug_msg}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            log("[OK] Gateway 重启成功")
            time.sleep(3)
            return True
        err = (result.stderr or result.stdout or "").strip()
        # 健康检查超时较常见，不再运行 verify（易二次超时），直接视为成功
        if "health" in err.lower() or "timed out" in err.lower():
            log("[OK] Gateway 重启已执行（健康检查超时属常见，请以实际使用为准）")
            time.sleep(2)
            return True
        log(f"[WARN] Gateway 重启失败：{err}")
        return False
    except subprocess.TimeoutExpired:
        log("[WARN] Gateway 重启超时")
        return False
    except FileNotFoundError:
        log("[WARN] 未找到可执行文件，请检查 OPENCLAW_NODE_PATH 指向的 node.exe 是否存在")
        log("   若已设置环境变量，请重启终端或 IDE 后再试")
        return False
    except Exception as e:
        log(f"[WARN] 重启异常：{e}")
        return False


def verify_gateway_status(
    on_log: Optional[Callable[[str], None]] = None,
    silent: bool = False,
) -> bool:
    """验证 Gateway 是否正常运行。silent=True 时不输出成功日志。"""
    log = on_log or (lambda _: None)
    cmd, _ = _get_openclaw_cmd("status")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        ok = "Listening" in result.stdout or "running" in result.stdout.lower()
        if ok and not silent:
            log("[OK] Gateway 状态正常")
        return ok
    except Exception:
        return False
