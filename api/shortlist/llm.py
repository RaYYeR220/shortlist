import json
from dataclasses import dataclass, field

from openai import AsyncOpenAI


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict
    raw_arguments: str


@dataclass(frozen=True)
class ChatReply:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)


class LLM:
    def __init__(self, base_url: str, api_key: str, client: AsyncOpenAI | None = None):
        self.client = client or AsyncOpenAI(base_url=base_url, api_key=api_key or "unset", timeout=60, max_retries=2)

    async def chat(self, *, model: str, messages: list[dict], tools: list[dict] | None = None,
                   temperature: float = 0.2, json_mode: bool = False) -> ChatReply:
        kwargs: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "extra_body": {"venice_parameters": {"include_venice_system_prompt": False}},
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = await self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        calls = []
        for tc in message.tool_calls or []:
            raw = tc.function.arguments or "{}"
            try:
                parsed = json.loads(raw)
                arguments = parsed if isinstance(parsed, dict) else {"__unparseable__": raw}
            except json.JSONDecodeError:
                arguments = {"__unparseable__": raw}
            calls.append(ToolCall(tc.id, tc.function.name, arguments, raw))
        usage = response.usage.model_dump() if response.usage else {}
        return ChatReply(message.content, calls, usage)

    @staticmethod
    def assistant_message(reply: ChatReply) -> dict:
        message: dict = {"role": "assistant", "content": reply.content or ""}
        if reply.tool_calls:
            message["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.raw_arguments}}
                for c in reply.tool_calls
            ]
        return message
