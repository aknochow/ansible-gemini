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


def make_response(candidates, usage_kwargs=None):
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
