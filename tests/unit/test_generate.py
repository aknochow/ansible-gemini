# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_genai():
    mock_google = MagicMock()
    mock_genai_module = MagicMock()
    mock_genai_module.Client = MagicMock()
    mock_google.genai = mock_genai_module
    sys.modules["google"] = mock_google
    sys.modules["google.genai"] = mock_genai_module
    sys.modules["google.genai.types"] = MagicMock()
    mock_errors = MagicMock()
    mock_errors.APIError = type("APIError", (Exception,), {})
    sys.modules["google.genai.errors"] = mock_errors
    yield mock_genai_module
    sys.modules.pop("google.genai.errors", None)
    sys.modules.pop("google.genai.types", None)
    sys.modules.pop("google.genai", None)
    sys.modules.pop("google", None)


def make_part(text):
    part = MagicMock()
    part.text = text
    return part


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


class TestMainReportsChanged:
    def test_main_reports_changed_false(self, mock_genai, monkeypatch):
        from ansible_collections.aknochow.gemini.plugins.modules import generate as generate_module

        fake_module = MagicMock()
        fake_module.params = {
            "model": "gemini-3.6-flash",
            "contents": "hi",
            "max_output_tokens": 100,
            "system_instruction": None,
            "temperature": None,
            "top_p": None,
            "top_k": None,
            "stop_sequences": None,
            "thinking_budget": 0,
            "response_schema": None,
            "response_mime_type": None,
            "backend": "api",
            "api_key": "test-key",
            "project_id": None,
            "location": None,
        }
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


class TestMainStructuredOutputConfig:
    def _run_main(self, mock_genai, monkeypatch, params_overrides):
        from ansible_collections.aknochow.gemini.plugins.modules import generate as generate_module

        fake_module = MagicMock()
        fake_module.params = {
            "model": "gemini-3.6-flash",
            "contents": "hi",
            "max_output_tokens": 100,
            "system_instruction": None,
            "temperature": None,
            "top_p": None,
            "top_k": None,
            "stop_sequences": None,
            "thinking_budget": 0,
            "response_schema": None,
            "response_mime_type": None,
            "backend": "api",
            "api_key": "test-key",
            "project_id": None,
            "location": None,
        }
        fake_module.params.update(params_overrides)
        mock_genai.Client.return_value.models.generate_content.return_value = make_response(
            [make_candidate([make_part("hi")])]
        )
        monkeypatch.setattr(generate_module, "AnsibleModule", lambda **kwargs: fake_module)

        generate_module.main()

        return mock_genai.types.GenerateContentConfig.call_args.kwargs

    def test_response_mime_type_defaults_to_json_when_schema_set(self, mock_genai, monkeypatch):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        config_kwargs = self._run_main(mock_genai, monkeypatch, {"response_schema": schema})

        assert config_kwargs["response_schema"] == schema
        assert config_kwargs["response_mime_type"] == "application/json"

    def test_explicit_response_mime_type_is_not_overridden(self, mock_genai, monkeypatch):
        schema = {"type": "object"}
        config_kwargs = self._run_main(
            mock_genai,
            monkeypatch,
            {"response_schema": schema, "response_mime_type": "text/plain"},
        )

        assert config_kwargs["response_mime_type"] == "text/plain"

    def test_no_response_schema_key_when_not_requested(self, mock_genai, monkeypatch):
        config_kwargs = self._run_main(mock_genai, monkeypatch, {})

        assert "response_schema" not in config_kwargs
        assert "response_mime_type" not in config_kwargs
