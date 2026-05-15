from __future__ import annotations

CONNECTOR_TYPES = ("ai_platform", "ai_code_tool", "mcp_server", "output_surface", "skill_platform", "api_connector")

CONNECTOR_CATALOG: list[dict[str, str]] = [
    # ── AI Platforms ──
    {
        "name": "Claude (Anthropic)",
        "category": "AI Platform",
        "use_case": "Best for nuanced instruction-following, long-form reasoning, analysis, and structured output generation.",
        "url": "https://claude.ai",
        "connector_type": "ai_platform",
        "trigger_keywords": "reasoning analysis essay research writing strategy planning legal",
    },
    {
        "name": "ChatGPT (OpenAI)",
        "category": "AI Platform",
        "use_case": "Best for creative writing, brainstorming, code generation, and general-purpose Q&A with tool-use support.",
        "url": "https://chatgpt.com",
        "connector_type": "ai_platform",
        "trigger_keywords": "creative writing brainstorm gpt-4o gpt-5 chatgpt openai copy marketing",
    },
    {
        "name": "Gemini (Google)",
        "category": "AI Platform",
        "use_case": "Best for multi-modal tasks, research, data analysis, and tasks requiring web-grounding.",
        "url": "https://gemini.google.com",
        "connector_type": "ai_platform",
        "trigger_keywords": "gemini gemini-pro gemini-flash multi-modal research data analysis",
    },
    {
        "name": "Groq",
        "category": "AI Platform",
        "use_case": "Best for high-speed inference on open models (Llama, Mixtral). Ideal for rapid iteration and prototyping.",
        "url": "https://groq.com",
        "connector_type": "ai_platform",
        "trigger_keywords": "groq llama mixtral fast inference open source low-latency",
    },

    # ── AI Code Tools ──
    {
        "name": "Cursor",
        "category": "AI Code Tool",
        "use_case": "Best for AI-native code editing with full IDE context. Use this prompt with Cursor Composer for multi-file changes.",
        "url": "https://cursor.sh",
        "connector_type": "ai_code_tool",
        "trigger_keywords": "cursor ide code editor composer agent",
    },
    {
        "name": "Windsurf",
        "category": "AI Code Tool",
        "use_case": "Best for agentic code editing with deep file-system context and multi-step autonomous coding.",
        "url": "https://codeium.com/windsurf",
        "connector_type": "ai_code_tool",
        "trigger_keywords": "windsurf codeium agentic code cascade",
    },
    {
        "name": "Cline",
        "category": "AI Code Tool",
        "use_case": "Best for VS Code agent with MCP support and autonomous task execution across your codebase.",
        "url": "https://github.com/cline/cline",
        "connector_type": "ai_code_tool",
        "trigger_keywords": "cline vs-code claude-dev mcp autonomous",
    },
    {
        "name": "Devin",
        "category": "AI Code Tool",
        "use_case": "Best for fully autonomous software engineering — planning, coding, testing, and deploying from a single prompt.",
        "url": "https://devin.ai",
        "connector_type": "ai_code_tool",
        "trigger_keywords": "devin autonomous engineer planning deployment",
    },
    {
        "name": "v0 by Vercel",
        "category": "AI UI Builder",
        "use_case": "Best for generating production-ready React/Next.js UI components from text prompts. Outputs ShadCN + Tailwind.",
        "url": "https://v0.dev",
        "connector_type": "ai_code_tool",
        "trigger_keywords": "v0 vercel ui react nextjs component landing page frontend shadcn tailwind",
    },
    {
        "name": "Bolt.new",
        "category": "AI UI Builder",
        "use_case": "Best for full-stack app generation in-browser with instant preview. React Native + Expo support.",
        "url": "https://bolt.new",
        "connector_type": "ai_code_tool",
        "trigger_keywords": "bolt full-stack app generation preview react-native expo stackblitz",
    },
    {
        "name": "Lovable",
        "category": "AI UI Builder",
        "use_case": "Best for non-developers building full-stack apps with auth, database, and frontend from a single prompt.",
        "url": "https://lovable.dev",
        "connector_type": "ai_code_tool",
        "trigger_keywords": "lovable full-stack no-code supabase auth database",
    },
    {
        "name": "Replit",
        "category": "AI Code Tool",
        "use_case": "Best for collaborative in-browser development with AI code generation and instant deployment.",
        "url": "https://replit.com",
        "connector_type": "ai_code_tool",
        "trigger_keywords": "replit browser ide collaborate deploy ghostwriter",
    },

    # ── Output Surfaces ──
    {
        "name": "Midjourney",
        "category": "Image Generation",
        "use_case": "Best for generating high-quality artistic images, concept art, and design assets from text prompts.",
        "url": "https://midjourney.com",
        "connector_type": "output_surface",
        "trigger_keywords": "midjourney image art design visual concept illustration style",
    },
    {
        "name": "Gamma",
        "category": "Presentation Tool",
        "use_case": "Best for turning structured prompts into slide-ready presentations with AI-generated layout and design.",
        "url": "https://gamma.app",
        "connector_type": "output_surface",
        "trigger_keywords": "gamma presentation slides deck pitch deck slide",
    },
    {
        "name": "DALL-E (OpenAI)",
        "category": "Image Generation",
        "use_case": "Best for generating images from detailed text descriptions with strong composition and text rendering.",
        "url": "https://openai.com/dall-e",
        "connector_type": "output_surface",
        "trigger_keywords": "dall-e image generation dalle openai art visual",
    },
    {
        "name": "Figma",
        "category": "Design Tool",
        "use_case": "Best for collaborative UI/UX design. Use this prompt with Figma AI or plugin ecosystem.",
        "url": "https://figma.com",
        "connector_type": "output_surface",
        "trigger_keywords": "figma design ui ux prototype wireframe mockup",
    },
    {
        "name": "Framer",
        "category": "No-Code Builder",
        "use_case": "Best for no-code landing pages with built-in CMS, animations, and publishing.",
        "url": "https://framer.com",
        "connector_type": "output_surface",
        "trigger_keywords": "framer landing page no-code animation publish cms",
    },
    {
        "name": "Canva",
        "category": "Design Tool",
        "use_case": "Best for quick visual content — social media graphics, presentations, documents, and brand assets.",
        "url": "https://canva.com",
        "connector_type": "output_surface",
        "trigger_keywords": "canva design social media graphic presentation brand",
    },

    # ── MCP Servers (connector ecosystem) ──
    {
        "name": "Postgres MCP",
        "category": "Database Connector",
        "use_case": "Connect AI agents directly to your Postgres database for schema-aware query generation and data analysis.",
        "url": "https://github.com/modelcontextprotocol/servers",
        "connector_type": "mcp_server",
        "trigger_keywords": "postgres database sql query data schema",
    },
    {
        "name": "Stripe MCP",
        "category": "Payment Connector",
        "use_case": "Enable AI agents to interact with Stripe — list transactions, manage customers, generate reports.",
        "url": "https://github.com/stripe/agent-toolkit",
        "connector_type": "mcp_server",
        "trigger_keywords": "stripe payment billing subscription transaction invoice",
    },
    {
        "name": "GitHub MCP",
        "category": "Code Repository Connector",
        "use_case": "Let AI agents read, create, and manage repositories, issues, pull requests, and code reviews.",
        "url": "https://github.com/modelcontextprotocol/servers",
        "connector_type": "mcp_server",
        "trigger_keywords": "github repository pr pull request issue code review git",
    },
    {
        "name": "Slack MCP",
        "category": "Communication Connector",
        "use_case": "Enable AI agents to read and send Slack messages, search channels, and manage notifications.",
        "url": "https://github.com/modelcontextprotocol/servers",
        "connector_type": "mcp_server",
        "trigger_keywords": "slack message channel notification communication team",
    },
    {
        "name": "Brave Search MCP",
        "category": "Web Search Connector",
        "use_case": "Give AI agents real-time web search capability for fact-checking, research, and current events.",
        "url": "https://github.com/modelcontextprotocol/servers",
        "connector_type": "mcp_server",
        "trigger_keywords": "search web research fact-check current events browse",
    },
    {
        "name": "Filesystem MCP",
        "category": "File System Connector",
        "use_case": "Enable AI agents to read, write, and navigate the local filesystem with configurable access controls.",
        "url": "https://github.com/modelcontextprotocol/servers",
        "connector_type": "mcp_server",
        "trigger_keywords": "filesystem file read write directory navigate local",
    },

    # ── Skill Platforms ──
    {
        "name": "OpenCode Skills",
        "category": "Agent Skill Platform",
        "use_case": "Install pre-built agent skills for browser testing, code review, QA, shipping, and more. Extend agent capabilities without code.",
        "url": "https://opencode.ai",
        "connector_type": "skill_platform",
        "trigger_keywords": "opencode skill agent browser qa review ship",
    },
    {
        "name": "Claude Code Tools",
        "category": "Agent Skill Platform",
        "use_case": "Extend Claude Code with custom hooks, MCP servers, and tools for specialized workflows.",
        "url": "https://docs.anthropic.com/en/docs/claude-code",
        "connector_type": "skill_platform",
        "trigger_keywords": "claude code hook mcp tool extension custom",
    },
    {
        "name": "Cline MCP Plugins",
        "category": "Agent Skill Platform",
        "use_case": "Add MCP servers to Cline for database access, API integration, and custom tool execution.",
        "url": "https://github.com/cline/cline",
        "connector_type": "skill_platform",
        "trigger_keywords": "cline mcp plugin server tool integration",
    },
]

_TRIGGER_INDEX: list[tuple[list[str], dict[str, str]]] | None = None


def _build_index():
    global _TRIGGER_INDEX
    if _TRIGGER_INDEX is not None:
        return
    _TRIGGER_INDEX = []
    for entry in CONNECTOR_CATALOG:
        keywords = entry.get("trigger_keywords", "").lower().split()
        _TRIGGER_INDEX.append((keywords, entry))


def load_connector_catalog() -> list[dict[str, str]]:
    return CONNECTOR_CATALOG


def recommend_connectors(prompt: str, limit: int = 4) -> list[dict[str, str]]:
    _build_index()
    prompt_l = prompt.lower()
    scored: list[tuple[int, dict[str, str]]] = []
    for keywords, entry in _TRIGGER_INDEX:
        score = sum(2 for kw in keywords if kw in prompt_l)
        if score > 0:
            scored.append((score, entry))

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for _, entry in scored:
        name = entry["name"]
        if name in seen:
            continue
        seen.add(name)
        result.append({
            "name": name,
            "category": entry["category"],
            "use_case": entry["use_case"],
            "url": entry.get("url", ""),
            "connector_type": entry["connector_type"],
        })
        if len(result) >= limit:
            break
    return result


def connector_catalog_summary(limit: int = 20) -> list[dict[str, str]]:
    return [
        {"name": e["name"], "category": e["category"], "connector_type": e["connector_type"]}
        for e in CONNECTOR_CATALOG[:limit]
    ]
