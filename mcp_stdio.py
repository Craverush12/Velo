#!/usr/bin/env python
"""
Velocity MCP stdio shim.

Usage:
  python mcp_stdio.py              # run as stdio MCP server
  python mcp_stdio.py --install    # auto-install into Claude Code / Claude Desktop config
"""
import asyncio
import json
import os
import pathlib
import platform
import sys

from dotenv import load_dotenv

load_dotenv()


def _install():
    script_path = str(pathlib.Path(__file__).resolve())
    entry = {
        "command": sys.executable,
        "args": [script_path],
        "env": {
            "VELOCITY_USER_ID": os.getenv("VELOCITY_USER_ID", "default"),
            "VELOCITY_API_URL": os.getenv("VELOCITY_API_URL", "http://localhost:8000"),
            "GROQ_API_KEY": os.getenv("GROQ_API_KEY", ""),
        },
    }

    home = pathlib.Path.home()
    installed = []

    # ── Claude Code ────────────────────────────────────────────────
    cc_config = home / ".claude" / "settings.json"
    if cc_config.parent.exists():
        cfg = {}
        if cc_config.exists():
            cfg = json.loads(cc_config.read_text(encoding="utf-8"))
        cfg.setdefault("mcpServers", {})["velocity"] = entry
        cc_config.parent.mkdir(parents=True, exist_ok=True)
        cc_config.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        installed.append(f"Claude Code: {cc_config}")

    # ── Claude Desktop ─────────────────────────────────────────────
    system = platform.system()
    if system == "Windows":
        cd_config = pathlib.Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    elif system == "Darwin":
        cd_config = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        cd_config = home / ".config" / "Claude" / "claude_desktop_config.json"

    if cd_config.parent.exists():
        cfg = {}
        if cd_config.exists():
            cfg = json.loads(cd_config.read_text(encoding="utf-8"))
        cfg.setdefault("mcpServers", {})["velocity"] = entry
        cd_config.parent.mkdir(parents=True, exist_ok=True)
        cd_config.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        installed.append(f"Claude Desktop: {cd_config}")

    if not installed:
        print("No Claude config directories found.")
        print(f"Manual config entry:\n{json.dumps({'velocity': entry}, indent=2)}")
        return

    for loc in installed:
        print(f"✓ Installed to {loc}")
    print(f"\nVELOCITY_USER_ID = {entry['env']['VELOCITY_USER_ID']}")
    print("Restart Claude to pick up the new server.")


async def _run_stdio():
    from mcp.server.stdio import stdio_server
    from core.mcp_tools import mcp_server

    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
        )


if __name__ == "__main__":
    if "--install" in sys.argv:
        _install()
    else:
        asyncio.run(_run_stdio())
