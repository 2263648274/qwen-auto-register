"""Entry point for Qwen token auto-acquisition."""

import argparse
import os
import sys
from pathlib import Path


def _load_env_if_exists() -> None:
    """Load .env from current directory or project root when available."""
    try:
        from dotenv import load_dotenv
    except Exception:
        return

    load_dotenv(Path.cwd() / ".env")
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse runtime mode and web binding options."""
    default_mode = (os.environ.get("AUTO_REGISTER_UI_MODE") or "web").strip().lower()
    if default_mode not in ("web", "gui"):
        default_mode = "web"

    parser = argparse.ArgumentParser(description="AutoRegister runner")
    parser.add_argument("--mode", choices=["web", "gui"], default=default_mode, help="Runtime UI mode")
    parser.add_argument("--host", default=os.environ.get("AUTO_REGISTER_HOST", "0.0.0.0"), help="Web bind host")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("AUTO_REGISTER_PORT", "18080")),
        help="Web bind port",
    )
    return parser.parse_args(argv)


def main() -> int:
    """Launch web or desktop UI. Returns exit code."""
    _load_env_if_exists()
    args = _parse_args(sys.argv[1:])

    if args.mode == "gui":
        from .gui.app import run_gui

        try:
            return run_gui()
        except KeyboardInterrupt:
            return 0

    from .web.app import run_web

    try:
        return run_web(host=args.host, port=args.port)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
