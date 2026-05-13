from __future__ import annotations

import importlib.util
from pathlib import Path


_TOOLS_PATH = Path(__file__).parent.parent / "mcp" / "tools.py"
_SPEC = importlib.util.spec_from_file_location("thinkvelocity_mcp_tools", _TOOLS_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Unable to load MCP tools from {_TOOLS_PATH}")

_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

mcp_server = _MODULE.mcp_server
list_tools = _MODULE.list_tools
call_tool = _MODULE.call_tool

for _name in dir(_MODULE):
    if _name.startswith("__"):
        continue
    globals().setdefault(_name, getattr(_MODULE, _name))
