# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock


def make_part(text=None, function_call=None):
    part = MagicMock()
    part.text = text
    # Same MagicMock auto-vivification hazard as response.parsed below --
    # must be set explicitly or every part looks like it made a function
    # call.
    part.function_call = function_call
    return part


def make_function_call(call_id="call_1", name="get_weather", args=None):
    function_call = MagicMock()
    function_call.id = call_id
    function_call.name = name
    function_call.args = args if args is not None else {"location": "Boston"}
    return function_call


# Shared by every TestMain* class below so each new module param only needs
# adding here once, instead of in every fake_module.params dict.
DEFAULT_MODULE_PARAMS = {
    "model": "gemini-3.6-flash",
    "contents": "hi",
    "max_output_tokens": 100,
    "system_instruction": None,
    "temperature": None,
    "top_p": None,
    "top_k": None,
    "stop_sequences": None,
    "thinking_budget": 0,
    "thinking_level": None,
    "response_schema": None,
    "response_mime_type": None,
    "tools": None,
    "tool_config": None,
    "labels": None,
    "backend": "api",
    "api_key": "test-key",
    "project_id": None,
    "location": None,
    "timeout": None,
    "max_retries": None,
}


def make_candidate(parts, finish_reason="STOP"):
    candidate = MagicMock()
    candidate.content.parts = parts
    candidate.finish_reason = finish_reason
    return candidate


def make_response(candidates, usage_kwargs=None, parsed=None):
    response = MagicMock()
    response.candidates = candidates
    usage = MagicMock()
    defaults = dict(
        prompt_token_count=10,
        candidates_token_count=5,
        total_token_count=15,
        cached_content_token_count=None,
        thoughts_token_count=None,
    )
    defaults.update(usage_kwargs or {})
    for k, v in defaults.items():
        setattr(usage, k, v)
    response.usage_metadata = usage
    response.model_dump.return_value = {"model_version": "gemini-3.5-flash"}
    # MagicMock auto-vivifies attributes as truthy MagicMocks, so this must
    # be set explicitly -- otherwise flatten_response's `is not None` check
    # on .parsed would spuriously fire for every test that doesn't care
    # about structured output.
    response.parsed = parsed
    return response


class TestFlattenResponse:
    def test_text_only_response(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.modules.generate import (
            flatten_response,
        )

        response = make_response([make_candidate([make_part("hello world")])])
        result = flatten_response(response)

        assert result["text"] == "hello world"
        assert result["finish_reason"] == "STOP"
        assert result["usage"]["prompt_token_count"] == 10
        assert result["usage"]["candidates_token_count"] == 5

    def test_multiple_parts_concatenated(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.modules.generate import (
            flatten_response,
        )

        response = make_response(
            [make_candidate([make_part("hello "), make_part("world")])]
        )
        result = flatten_response(response)

        assert result["text"] == "hello world"

    def test_no_candidates(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.modules.generate import (
            flatten_response,
        )

        response = make_response([])
        result = flatten_response(response)

        assert result["text"] == ""
        assert result["finish_reason"] is None

    def test_cached_content_usage_field(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.modules.generate import (
            flatten_response,
        )

        response = make_response(
            [make_candidate([make_part("hi")])],
            usage_kwargs={"cached_content_token_count": 100},
        )
        result = flatten_response(response)

        assert result["usage"]["cached_content_token_count"] == 100

    def test_response_passthrough(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.modules.generate import (
            flatten_response,
        )

        response = make_response([make_candidate([make_part("hi")])])
        result = flatten_response(response)

        assert result["response"] == {"model_version": "gemini-3.5-flash"}

    def test_structured_present_when_parsed(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.modules.generate import (
            flatten_response,
        )

        response = make_response(
            [make_candidate([make_part('{"name": "bug", "severity": "high"}')])],
            parsed={"name": "bug", "severity": "high"},
        )
        result = flatten_response(response)

        assert result["structured"] == {"name": "bug", "severity": "high"}

    def test_structured_absent_when_not_requested(self, mock_genai):
        # Regression check: a plain conversational reply must not gain a
        # `structured` key just because response.parsed happens to be
        # truthy -- it's only ever non-None when response_schema was set
        # on the request, but this pins the flatten_response-side contract
        # directly (mirrors aknochow.claude's flatten_response-leak fix).
        from ansible_collections.aknochow.gemini.plugins.modules.generate import (
            flatten_response,
        )

        response = make_response([make_candidate([make_part("hi")])], parsed=None)
        result = flatten_response(response)

        assert "structured" not in result

    def test_tool_calls_present_when_function_call_part(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.modules.generate import (
            flatten_response,
        )

        function_call = make_function_call(
            call_id="call_1", name="get_weather", args={"location": "Boston"}
        )
        response = make_response([make_candidate([make_part(function_call=function_call)])])
        result = flatten_response(response)

        assert result["tool_calls"] == [
            {"id": "call_1", "name": "get_weather", "args": {"location": "Boston"}}
        ]

    def test_tool_calls_empty_when_no_function_calls(self, mock_genai):
        # Regression check: a plain text-only response must get an empty
        # list, not a spuriously "truthy" MagicMock-vivified function_call
        # mistaken for a real one (see make_part's own comment).
        from ansible_collections.aknochow.gemini.plugins.modules.generate import (
            flatten_response,
        )

        response = make_response([make_candidate([make_part("hi")])])
        result = flatten_response(response)

        assert result["tool_calls"] == []

    def test_tool_calls_mixed_with_text(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.modules.generate import (
            flatten_response,
        )

        function_call = make_function_call()
        text_part = make_part("Let me check that.")
        call_part = make_part(function_call=function_call)
        response = make_response([make_candidate([text_part, call_part])])
        result = flatten_response(response)

        assert result["text"] == "Let me check that."
        assert len(result["tool_calls"]) == 1


class TestMainReportsChanged:
    def test_main_reports_changed_false(self, mock_genai, monkeypatch):
        from ansible_collections.aknochow.gemini.plugins.modules import generate as generate_module

        fake_module = MagicMock()
        fake_module.params = dict(DEFAULT_MODULE_PARAMS)
        mock_genai.Client.return_value.models.generate_content.return_value = make_response(
            [make_candidate([make_part("hi")])]
        )
        monkeypatch.setattr(generate_module, "AnsibleModule", lambda **kwargs: fake_module)

        generate_module.main()

        fake_module.exit_json.assert_called_once()
        # Regression check: a query call never mutates infrastructure
        # state, so this must always be False -- not just "whatever the
        # response happened to produce". Fails against the pre-fix
        # hardcoded changed=True.
        assert fake_module.exit_json.call_args.kwargs["changed"] is False


def run_main_and_get_config_kwargs(mock_genai, monkeypatch, params_overrides):
    from ansible_collections.aknochow.gemini.plugins.modules import generate as generate_module

    fake_module = MagicMock()
    fake_module.params = dict(DEFAULT_MODULE_PARAMS)
    fake_module.params.update(params_overrides)
    mock_genai.Client.return_value.models.generate_content.return_value = make_response(
        [make_candidate([make_part("hi")])]
    )
    monkeypatch.setattr(generate_module, "AnsibleModule", lambda **kwargs: fake_module)

    generate_module.main()

    return mock_genai.types.GenerateContentConfig.call_args.kwargs


class TestMainStructuredOutputConfig:
    def test_response_mime_type_defaults_to_json_when_schema_set(self, mock_genai, monkeypatch):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        config_kwargs = run_main_and_get_config_kwargs(mock_genai, monkeypatch, {"response_schema": schema})

        assert config_kwargs["response_schema"] == schema
        assert config_kwargs["response_mime_type"] == "application/json"

    def test_explicit_response_mime_type_is_not_overridden(self, mock_genai, monkeypatch):
        schema = {"type": "object"}
        config_kwargs = run_main_and_get_config_kwargs(
            mock_genai,
            monkeypatch,
            {"response_schema": schema, "response_mime_type": "text/plain"},
        )

        assert config_kwargs["response_mime_type"] == "text/plain"

    def test_no_response_schema_key_when_not_requested(self, mock_genai, monkeypatch):
        config_kwargs = run_main_and_get_config_kwargs(mock_genai, monkeypatch, {})

        assert "response_schema" not in config_kwargs
        assert "response_mime_type" not in config_kwargs


class TestMainToolsConfig:
    def test_tools_and_tool_config_passed_through(self, mock_genai, monkeypatch):
        tools = [
            {
                "function_declarations": [
                    {
                        "name": "get_weather",
                        "description": "Get the weather for a location",
                        "parameters": {
                            "type": "object",
                            "properties": {"location": {"type": "string"}},
                            "required": ["location"],
                        },
                    }
                ]
            }
        ]
        tool_config = {"function_calling_config": {"mode": "ANY"}}
        config_kwargs = run_main_and_get_config_kwargs(
            mock_genai, monkeypatch, {"tools": tools, "tool_config": tool_config}
        )

        assert config_kwargs["tools"] == tools
        assert config_kwargs["tool_config"] == tool_config

    def test_no_tools_key_when_not_requested(self, mock_genai, monkeypatch):
        config_kwargs = run_main_and_get_config_kwargs(mock_genai, monkeypatch, {})

        assert "tools" not in config_kwargs
        assert "tool_config" not in config_kwargs


class TestMainLabels:
    def test_labels_passed_through(self, mock_genai, monkeypatch):
        labels = {"team": "platform", "pipeline": "review"}
        config_kwargs = run_main_and_get_config_kwargs(mock_genai, monkeypatch, {"labels": labels})

        assert config_kwargs["labels"] == labels

    def test_no_labels_key_when_not_requested(self, mock_genai, monkeypatch):
        config_kwargs = run_main_and_get_config_kwargs(mock_genai, monkeypatch, {})

        assert "labels" not in config_kwargs


class TestMainThinkingConfig:
    def test_no_thinking_config_when_budget_zero_and_level_none(self, mock_genai, monkeypatch):
        config_kwargs = run_main_and_get_config_kwargs(
            mock_genai, monkeypatch, {"thinking_budget": 0, "thinking_level": None}
        )
        assert "thinking_config" not in config_kwargs

    def test_thinking_budget_passed_when_greater_than_zero(self, mock_genai, monkeypatch):
        config_kwargs = run_main_and_get_config_kwargs(
            mock_genai, monkeypatch, {"thinking_budget": 1024}
        )
        mock_genai.types.ThinkingConfig.assert_called_with(thinking_budget=1024)
        assert "thinking_config" in config_kwargs

    def test_thinking_level_passed_when_specified(self, mock_genai, monkeypatch):
        config_kwargs = run_main_and_get_config_kwargs(
            mock_genai, monkeypatch, {"thinking_level": "high"}
        )
        mock_genai.types.ThinkingConfig.assert_called_with(thinking_level="high")
        assert "thinking_config" in config_kwargs

    def test_both_thinking_budget_and_level_passed(self, mock_genai, monkeypatch):
        config_kwargs = run_main_and_get_config_kwargs(
            mock_genai, monkeypatch, {"thinking_budget": 512, "thinking_level": "medium"}
        )
        mock_genai.types.ThinkingConfig.assert_called_with(thinking_budget=512, thinking_level="medium")
        assert "thinking_config" in config_kwargs

