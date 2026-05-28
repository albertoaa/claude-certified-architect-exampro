"""Tests for agent_output_parser.formatter."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from claude_agent_sdk.types import (
    AssistantMessage,
    HookEventMessage,
    MirrorErrorMessage,
    RateLimitEvent,
    RateLimitInfo,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_output_parser.formatter import (
    _format_tool_input,
    format_message,
    print_message,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_assistant(*blocks, model="claude-sonnet-4-6", error=None):
    return AssistantMessage(
        content=list(blocks),
        model=model,
        parent_tool_use_id=None,
        error=error,
        usage=None,
        message_id=None,
        stop_reason=None,
        session_id=None,
        uuid=None,
    )


def make_result(*, result="done", is_error=False, cost=0.0123, turns=2,
                duration_ms=500, duration_api_ms=400, errors=None,
                usage=None):
    return ResultMessage(
        subtype="success",
        duration_ms=duration_ms,
        duration_api_ms=duration_api_ms,
        is_error=is_error,
        num_turns=turns,
        session_id="sess-abc",
        stop_reason="end_turn",
        total_cost_usd=cost,
        usage=usage or {"input_tokens": 10, "output_tokens": 5},
        result=result,
        structured_output=None,
        model_usage=None,
        permission_denials=None,
        deferred_tool_use=None,
        errors=errors,
        api_error_status=None,
        uuid=None,
    )


def make_rate_limit(status, rate_limit_type=None, utilization=None):
    info = RateLimitInfo(
        status=status,
        resets_at=None,
        rate_limit_type=rate_limit_type,
        utilization=utilization,
        overage_status=None,
        overage_resets_at=None,
        overage_disabled_reason=None,
        raw={},
    )
    return RateLimitEvent(rate_limit_info=info, uuid="u1", session_id="s1")


# ---------------------------------------------------------------------------
# _format_tool_input
# ---------------------------------------------------------------------------

class TestFormatToolInput:
    def test_bash_shows_command(self):
        assert _format_tool_input("Bash", {"command": "ls -la"}) == "ls -la"

    def test_bash_truncates_at_120(self):
        long_cmd = "x" * 150
        result = _format_tool_input("Bash", {"command": long_cmd})
        assert len(result) == 121  # 120 chars + ellipsis
        assert result.endswith("…")

    def test_bash_short_command_no_ellipsis(self):
        result = _format_tool_input("Bash", {"command": "echo hi"})
        assert "…" not in result

    def test_read_shows_file_path(self):
        assert _format_tool_input("Read", {"file_path": "/tmp/foo.py"}) == "/tmp/foo.py"

    def test_edit_shows_file_path(self):
        assert _format_tool_input("Edit", {"file_path": "/src/bar.py"}) == "/src/bar.py"

    def test_write_shows_file_path(self):
        assert _format_tool_input("Write", {"file_path": "/out.txt"}) == "/out.txt"

    def test_multiedit_shows_file_path(self):
        assert _format_tool_input("MultiEdit", {"file_path": "/a.py"}) == "/a.py"

    def test_generic_tool_shows_key_value(self):
        result = _format_tool_input("Search", {"query": "hello"})
        assert "query=" in result
        assert "hello" in result

    def test_generic_tool_truncates_long_value(self):
        result = _format_tool_input("Search", {"query": "x" * 100})
        assert "…" in result


# ---------------------------------------------------------------------------
# AssistantMessage
# ---------------------------------------------------------------------------

class TestAssistantMessage:
    def test_text_block(self):
        msg = make_assistant(TextBlock(text="Hello, world!"))
        assert format_message(msg) == "Hello, world!"

    def test_multiple_text_blocks_joined_by_newline(self):
        msg = make_assistant(TextBlock(text="Line 1"), TextBlock(text="Line 2"))
        result = format_message(msg)
        assert "Line 1" in result
        assert "Line 2" in result

    def test_thinking_block_shows_prefix(self):
        msg = make_assistant(ThinkingBlock(thinking="Some deep thought", signature="sig"))
        result = format_message(msg)
        assert result.startswith("[thinking]")
        assert "Some deep thought" in result

    def test_thinking_block_truncated_at_200(self):
        long_thought = "t" * 250
        msg = make_assistant(ThinkingBlock(thinking=long_thought, signature="sig"))
        result = format_message(msg)
        assert "…" in result
        # The thinking content after "[thinking] " should be 200 chars + ellipsis
        thinking_part = result.replace("[thinking] ", "")
        assert len(thinking_part) == 201  # 200 + ellipsis char

    def test_thinking_block_short_no_ellipsis(self):
        msg = make_assistant(ThinkingBlock(thinking="short", signature="sig"))
        result = format_message(msg)
        assert "…" not in result

    def test_tool_use_block_bash(self):
        msg = make_assistant(ToolUseBlock(id="t1", name="Bash", input={"command": "pwd"}))
        result = format_message(msg)
        assert "[tool: Bash]" in result
        assert "pwd" in result

    def test_tool_use_block_read(self):
        msg = make_assistant(ToolUseBlock(id="t2", name="Read", input={"file_path": "/foo.py"}))
        result = format_message(msg)
        assert "[tool: Read]" in result
        assert "/foo.py" in result

    def test_tool_result_block_success(self):
        msg = make_assistant(ToolResultBlock(tool_use_id="t1", content="ok", is_error=False))
        result = format_message(msg)
        assert "[tool result]" in result
        assert "ok" in result
        assert "ERROR" not in result

    def test_tool_result_block_error(self):
        msg = make_assistant(ToolResultBlock(tool_use_id="t1", content="boom", is_error=True))
        result = format_message(msg)
        assert "ERROR" in result
        assert "boom" in result

    def test_tool_result_block_list_content(self):
        content = [{"type": "text", "text": "file contents here"}]
        msg = make_assistant(ToolResultBlock(tool_use_id="t1", content=content, is_error=False))
        result = format_message(msg)
        assert "file contents here" in result

    def test_tool_result_block_none_content(self):
        msg = make_assistant(ToolResultBlock(tool_use_id="t1", content=None, is_error=False))
        result = format_message(msg)
        assert "[tool result]" in result

    def test_tool_result_block_truncates_long_content(self):
        long = "x" * 400
        msg = make_assistant(ToolResultBlock(tool_use_id="t1", content=long, is_error=False))
        result = format_message(msg)
        assert "…" in result

    def test_assistant_error_field_shown(self):
        msg = make_assistant(error="rate_limit")
        result = format_message(msg)
        assert "[assistant error: rate_limit]" in result

    def test_empty_content_returns_none(self):
        msg = make_assistant()
        assert format_message(msg) is None


# ---------------------------------------------------------------------------
# UserMessage
# ---------------------------------------------------------------------------

class TestUserMessage:
    def test_string_content_shown(self):
        msg = UserMessage(content="Hello", uuid=None, parent_tool_use_id=None, tool_use_result=None)
        result = format_message(msg)
        assert result == "[user] Hello"

    def test_list_content_returns_none(self):
        block = ToolResultBlock(tool_use_id="t1", content="ok", is_error=False)
        msg = UserMessage(content=[block], uuid=None, parent_tool_use_id=None, tool_use_result=None)
        assert format_message(msg) is None


# ---------------------------------------------------------------------------
# SystemMessage
# ---------------------------------------------------------------------------

class TestSystemMessage:
    def test_init_subtype_shows_model_and_session(self):
        msg = SystemMessage(
            subtype="init",
            data={"model": "claude-sonnet-4-6", "session_id": "abc12345xyz"},
        )
        result = format_message(msg)
        assert "[session]" in result
        assert "claude-sonnet-4-6" in result
        assert "abc12345" in result  # truncated to 8 chars

    def test_other_subtype_is_silent(self):
        msg = SystemMessage(subtype="unknown_event", data={})
        assert format_message(msg) is None


# ---------------------------------------------------------------------------
# RateLimitEvent
# ---------------------------------------------------------------------------

class TestRateLimitEvent:
    def test_allowed_is_silent(self):
        assert format_message(make_rate_limit("allowed")) is None

    def test_allowed_warning_shown(self):
        result = format_message(make_rate_limit("allowed_warning", "five_hour", 0.9))
        assert "[rate limit warning]" in result
        assert "five_hour" in result
        assert "90%" in result

    def test_rejected_shown(self):
        result = format_message(make_rate_limit("rejected", "seven_day"))
        assert "[rate limit reached]" in result
        assert "seven_day" in result

    def test_allowed_warning_no_utilization(self):
        result = format_message(make_rate_limit("allowed_warning", "five_hour"))
        assert "[rate limit warning]" in result


# ---------------------------------------------------------------------------
# Task messages
# ---------------------------------------------------------------------------

class TestTaskMessages:
    def test_task_started(self):
        msg = TaskStartedMessage(
            subtype="task_started",
            data={},
            task_id="t1",
            description="Fix the bug",
            uuid="u1",
            session_id="s1",
            tool_use_id=None,
            task_type=None,
        )
        result = format_message(msg)
        assert "[task started]" in result
        assert "Fix the bug" in result

    def test_task_progress_is_silent(self):
        from claude_agent_sdk.types import TaskUsage
        msg = TaskProgressMessage(
            subtype="task_progress",
            data={},
            task_id="t1",
            description="Working…",
            usage=TaskUsage(total_tokens=100, tool_uses=2, duration_ms=500),
            uuid="u1",
            session_id="s1",
            tool_use_id=None,
            last_tool_name=None,
        )
        assert format_message(msg) is None

    def test_task_notification_completed(self):
        msg = TaskNotificationMessage(
            subtype="task_notification",
            data={},
            task_id="t1",
            status="completed",
            output_file="/tmp/out",
            summary="All done",
            uuid="u1",
            session_id="s1",
            tool_use_id=None,
            usage=None,
        )
        result = format_message(msg)
        assert "[task completed]" in result
        assert "All done" in result

    def test_task_notification_failed(self):
        msg = TaskNotificationMessage(
            subtype="task_notification",
            data={},
            task_id="t1",
            status="failed",
            output_file="/tmp/out",
            summary="Went wrong",
            uuid="u1",
            session_id="s1",
            tool_use_id=None,
            usage=None,
        )
        result = format_message(msg)
        assert "[task failed]" in result

    def test_mirror_error(self):
        msg = MirrorErrorMessage(
            subtype="mirror_error",
            data={},
            key=None,
            error="Connection refused",
        )
        result = format_message(msg)
        assert "[mirror error]" in result
        assert "Connection refused" in result

    def test_hook_event_is_silent(self):
        msg = HookEventMessage(
            subtype="hook_started",
            data={},
            hook_event_name="PreToolUse",
            session_id=None,
            uuid=None,
        )
        assert format_message(msg) is None


# ---------------------------------------------------------------------------
# StreamEvent
# ---------------------------------------------------------------------------

class TestStreamEvent:
    def test_stream_event_is_silent(self):
        msg = StreamEvent(uuid="u1", session_id="s1", event={}, parent_tool_use_id=None)
        assert format_message(msg) is None


# ---------------------------------------------------------------------------
# Unknown type
# ---------------------------------------------------------------------------

class TestUnknownType:
    def test_unknown_object_returns_none(self):
        assert format_message("raw string") is None
        assert format_message(42) is None
        assert format_message(None) is None


# ---------------------------------------------------------------------------
# ResultMessage
# ---------------------------------------------------------------------------

class TestResultMessage:
    def test_success_result(self):
        result = format_message(make_result(result="Task complete.", turns=3, cost=0.005))
        assert "--- Result ---" in result
        assert "success" in result
        assert "turns   : 3" in result
        assert "$0.0050" in result
        assert "Task complete." in result

    def test_error_result(self):
        result = format_message(make_result(is_error=True, errors=["Something went wrong"]))
        assert "ERROR" in result
        assert "Something went wrong" in result

    def test_result_none_cost_shows_na(self):
        result = format_message(make_result(cost=None))
        assert "n/a" in result

    def test_result_truncates_long_text(self):
        result = format_message(make_result(result="r" * 600))
        assert "…" in result

    def test_token_counts_shown(self):
        result = format_message(make_result(usage={"input_tokens": 100, "output_tokens": 50}))
        assert "100" in result
        assert "50" in result

    def test_duration_shown(self):
        result = format_message(make_result(duration_ms=1234, duration_api_ms=900))
        assert "1234ms" in result
        assert "900ms" in result


# ---------------------------------------------------------------------------
# print_message
# ---------------------------------------------------------------------------

class TestPrintMessage:
    def test_prints_when_text_returned(self):
        msg = make_assistant(TextBlock(text="hi"))
        with patch("builtins.print") as mock_print:
            print_message(msg)
        mock_print.assert_called_once_with("hi")

    def test_does_not_print_when_none(self):
        msg = make_assistant()  # empty → None
        with patch("builtins.print") as mock_print:
            print_message(msg)
        mock_print.assert_not_called()

    def test_does_not_print_for_silent_types(self):
        msg = make_rate_limit("allowed")
        with patch("builtins.print") as mock_print:
            print_message(msg)
        mock_print.assert_not_called()
