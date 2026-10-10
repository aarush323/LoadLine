import json

from pydantic_ai.messages import FunctionToolCallEvent, FunctionToolResultEvent, ToolCallPart, ToolReturnPart

from loadline.ui.agent_trace import format_tool_call, format_tool_result


def _call_event(name: str, args: dict) -> FunctionToolCallEvent:
    return FunctionToolCallEvent(
        part=ToolCallPart(tool_name=name, args=json.dumps(args), tool_call_id="1"),
    )


def _result_event(name: str, payload: dict) -> FunctionToolResultEvent:
    return FunctionToolResultEvent(
        part=ToolReturnPart(tool_name=name, content=json.dumps(payload), tool_call_id="1"),
        content=json.dumps(payload),
    )


def test_format_run_k6_call_redacts_secrets():
    line = format_tool_call(
        _call_event(
            "run_k6",
            {
                "rate": 5,
                "duration_s": 10,
                "endpoints": [{"id": "login", "path": "/login"}],
                "auth": {"password": "nope"},
            },
        )
    )
    assert "nope" not in line
    assert "run_k6" in line


def test_format_repo_routes_result():
    line = format_tool_result(_result_event("repo", {"routes": [{"path": "/"}]}))
    assert "1 routes" in line


def test_format_read_file_from_part_content_only():
    event = FunctionToolResultEvent(
        part=ToolReturnPart(
            tool_name="read_file",
            content={"path": "app/main.py", "start_line": 1, "end_line": 40, "snippet": "1:x\n2:y"},
            tool_call_id="1",
        ),
        content=None,
    )
    line = format_tool_result(event)
    assert line == "← read_file 40 lines"


def test_format_run_k6_result_summary():
    line = format_tool_result(
        _result_event(
            "run_k6",
            {
                "experiment_id": "exp-k6-0001",
                "operations": {"health": {"p95_ms": 12.4, "error_count": 0}},
                "dropped_iterations": 0,
            },
        )
    )
    assert "exp-k6-0001" in line
    assert "p95_health=12ms" in line
