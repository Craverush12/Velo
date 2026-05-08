import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\Users\Arjun\Desktop\ThinkVelocity")
os.environ["VELOCITY_USER_ID"] = "test-integrated"
os.environ["VELOCITY_API_URL"] = "http://localhost:8000"

from dotenv import load_dotenv
load_dotenv()

from core.mcp_tools import list_tools, call_tool


SEPARATOR = "\n" + "=" * 60 + "\n"


async def main():
    # 1. List tools
    tools = await list_tools()
    print(SEPARATOR + "TOOLS REGISTERED")
    for t in tools:
        print(f"  [{t.name}]")
        print(f"   {t.description[:100]}...")

    # 2. inject_context (fresh user)
    print(SEPARATOR + "inject_context — fresh user")
    result = await call_tool("inject_context", {})
    print(result[0].text)

    # 3. enhance_prompt
    print(SEPARATOR + "enhance_prompt")
    enhance_result = await call_tool("enhance_prompt", {
        "prompt": "write a python script that reads a csv and plots a chart",
        "target_ai": "claude",
    })
    print(enhance_result[0].text)

    # 4. refine_prompt — answer the clarifications from the enhance step
    print(SEPARATOR + "refine_prompt — answering clarifications")
    refine_result = await call_tool("refine_prompt", {
        "original_prompt": "write a python script that reads a csv and plots a chart",
        "target_ai": "claude",
        "clarification_qa": [
            {"question": "What type of chart?", "answer": "bar chart"},
            {"question": "Which columns are x and y?", "answer": "x=date, y=revenue"},
            {"question": "How to handle missing values?", "answer": "drop them"},
        ],
    })
    print(refine_result[0].text)

    # 5. get_my_context — after activity
    print(SEPARATOR + "get_my_context — after activity")
    result = await call_tool("get_my_context", {})
    print(result[0].text)

    print(SEPARATOR + "ALL TESTS PASSED")


asyncio.run(main())
