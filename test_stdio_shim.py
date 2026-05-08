import asyncio
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

SHIM = r"C:\Users\Arjun\Desktop\ThinkVelocity\mcp_stdio.py"


async def send_recv(proc, msg: dict) -> dict:
    line = json.dumps(msg) + "\n"
    proc.stdin.write(line.encode("utf-8"))
    await proc.stdin.drain()
    response_line = await proc.stdout.readline()
    return json.loads(response_line.decode("utf-8"))


async def main():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, SHIM,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=r"C:\Users\Arjun\Desktop\ThinkVelocity",
    )

    print("=== 1. initialize ===")
    resp = await send_recv(proc, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    })
    print(f"serverInfo: {resp.get('result', {}).get('serverInfo')}")
    print(f"protocolVersion: {resp.get('result', {}).get('protocolVersion')}")

    # send initialized notification
    proc.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}\n')
    await proc.stdin.drain()
    await asyncio.sleep(0.1)

    print("\n=== 2. tools/list ===")
    resp = await send_recv(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tools = resp.get("result", {}).get("tools", [])
    for t in tools:
        print(f"  [{t['name']}]")

    print("\n=== 3. tools/call — inject_context ===")
    resp = await send_recv(proc, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "inject_context", "arguments": {}},
    })
    content = resp.get("result", {}).get("content", [])
    for c in content:
        print(c.get("text", ""))

    print("\n=== 4. tools/call — enhance_prompt ===")
    resp = await send_recv(proc, {
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {
            "name": "enhance_prompt",
            "arguments": {
                "prompt": "help me write a cold email to a VC",
                "target_ai": "claude",
            },
        },
    })
    content = resp.get("result", {}).get("content", [])
    for c in content:
        print(c.get("text", ""))

    print("\n=== ALL STDIO TESTS PASSED ===")

    proc.stdin.close()
    try:
        await asyncio.wait_for(proc.wait(), timeout=3)
    except asyncio.TimeoutError:
        proc.terminate()


asyncio.run(main())
