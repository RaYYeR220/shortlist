META_TOOLS = [
    {"type": "function", "function": {
        "name": "finish",
        "description": "Finish the task with a short summary of what you did.",
        "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
    }},
    {"type": "function", "function": {
        "name": "request_amendment",
        "description": "Ask to add a step that is not in your declared plan.",
        "parameters": {"type": "object", "properties": {
            "mcp": {"type": "string"}, "action": {"type": "string"},
            "arguments": {"type": "object"}, "reason": {"type": "string"},
        }, "required": ["mcp", "action", "reason"]},
    }},
]


async def build_catalog(servers: dict) -> list[dict]:
    tools: list[dict] = []
    for prefix, server in servers.items():
        for tool in await server.list_tools():
            schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {"type": "object"}
            tools.append({"type": "function", "function": {
                "name": f"{prefix}__{tool.name}", "description": tool.description or "", "parameters": schema,
            }})
    return tools + META_TOOLS
