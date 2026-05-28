from __future__ import annotations

from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    UserMessage,
    SystemMessage,
    ResultMessage,
    RateLimitEvent,
    StreamEvent,
)
from claude_agent_sdk.types import (
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    ToolResultBlock,
    TaskStartedMessage,
    TaskProgressMessage,
    TaskNotificationMessage,
    MirrorErrorMessage,
    HookEventMessage,
)

try:
    from claude_agent_sdk.types import ServerToolUseBlock, ServerToolResultBlock
    _HAS_SERVER_BLOCKS = True
except ImportError:
    _HAS_SERVER_BLOCKS = False


def _format_tool_input(name: str, input_dict: dict[str, Any]) -> str:
    if name == "Bash":
        cmd = input_dict.get("command", "")
        return cmd[:120] + ("…" if len(cmd) > 120 else "")
    if name in ("Read", "Edit", "Write", "MultiEdit"):
        return str(input_dict.get("file_path", ""))
    parts = []
    for k, v in input_dict.items():
        v_str = repr(v)
        parts.append(f"{k}={v_str[:60]}{'…' if len(v_str) > 60 else ''}")
    return ", ".join(parts)


def _format_tool_result_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content[:300] + ("…" if len(content) > 300 else "")
    if isinstance(content, list):
        parts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
        joined = " ".join(parts)
        return joined[:300] + ("…" if len(joined) > 300 else "")
    return str(content)[:300]


def _format_assistant(msg: AssistantMessage) -> str:
    lines = []
    if msg.error is not None:
        lines.append(f"[assistant error: {msg.error}]")
    for block in msg.content:
        if isinstance(block, TextBlock):
            lines.append(block.text)
        elif isinstance(block, ThinkingBlock):
            truncated = block.thinking[:200] + ("…" if len(block.thinking) > 200 else "")
            lines.append(f"[thinking] {truncated}")
        elif isinstance(block, ToolUseBlock):
            summary = _format_tool_input(block.name, block.input)
            lines.append(f"[tool: {block.name}] {summary}")
        elif isinstance(block, ToolResultBlock):
            prefix = "ERROR " if block.is_error else ""
            content_str = _format_tool_result_content(block.content)
            lines.append(f"[tool result] {prefix}{content_str}")
        elif _HAS_SERVER_BLOCKS and isinstance(block, (ServerToolUseBlock, ServerToolResultBlock)):
            lines.append(f"[server-tool: {block.name}]")
    return "\n".join(lines)


def _format_result(msg: ResultMessage) -> str:
    status = "ERROR" if msg.is_error else "success"
    cost = f"${msg.total_cost_usd:.4f}" if msg.total_cost_usd is not None else "n/a"
    usage = msg.usage or {}
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    lines = [
        "--- Result ---",
        f"status  : {status}",
        f"turns   : {msg.num_turns}",
        f"time    : {msg.duration_ms}ms ({msg.duration_api_ms}ms API)",
        f"cost    : {cost}",
        f"tokens  : {input_tokens} in / {output_tokens} out",
        "--------------",
    ]
    if msg.errors:
        lines.append("errors  : " + "; ".join(msg.errors))
    if msg.result:
        result_text = msg.result[:500] + ("…" if len(msg.result) > 500 else "")
        lines.append(result_text)
    return "\n".join(lines)


def format_message(message: Any) -> str | None:
    if isinstance(message, ResultMessage):
        return _format_result(message)
    if isinstance(message, AssistantMessage):
        text = _format_assistant(message)
        return text if text.strip() else None
    if isinstance(message, UserMessage):
        if isinstance(message.content, str):
            return f"[user] {message.content}"
        return None
    if isinstance(message, RateLimitEvent):
        info = message.rate_limit_info
        if info.status == "allowed_warning":
            util = f" at {info.utilization:.0%}" if info.utilization is not None else ""
            return f"[rate limit warning] {info.rate_limit_type}{util}"
        if info.status == "rejected":
            return f"[rate limit reached] {info.rate_limit_type}"
        return None
    if isinstance(message, TaskStartedMessage):
        return f"[task started] {message.description}"
    if isinstance(message, TaskNotificationMessage):
        return f"[task {message.status}] {message.summary}"
    if isinstance(message, MirrorErrorMessage):
        return f"[mirror error] {message.error}"
    if isinstance(message, (TaskProgressMessage, HookEventMessage)):
        return None
    if isinstance(message, SystemMessage):
        if message.subtype == "init":
            data = message.data
            model = data.get("model", "?")
            session = str(data.get("session_id", "?"))[:8]
            return f"[session] model={model} session={session}"
        return None
    if isinstance(message, StreamEvent):
        return None
    return None


def print_message(message: Any) -> None:
    from ._logger import log
    text = format_message(message)
    if text:
        print(text)
        log(text)
