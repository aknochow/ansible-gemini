# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock

DEFAULT_MODULE_PARAMS = {
    "model": "gemini-3.6-flash",
    "contents": "hi",
    "system_instruction": None,
    "tools": None,
    "backend": "api",
    "api_key": "test-key",
    "project_id": None,
    "location": None,
    "timeout": None,
    "max_retries": None,
}


def run_main(mock_genai, monkeypatch, params_overrides, count_tokens_return=None):
    from ansible_collections.aknochow.gemini.plugins.modules import count_tokens as count_tokens_module

    fake_module = MagicMock()
    fake_module.params = dict(DEFAULT_MODULE_PARAMS)
    fake_module.params.update(params_overrides)

    response = count_tokens_return
    if response is None:
        response = MagicMock()
        response.total_tokens = 42
        response.cached_content_token_count = None
    mock_genai.Client.return_value.models.count_tokens.return_value = response

    monkeypatch.setattr(count_tokens_module, "AnsibleModule", lambda **kwargs: fake_module)

    count_tokens_module.main()

    return fake_module


class TestMainReportsResults:
    def test_returns_total_tokens_and_changed_false(self, mock_genai, monkeypatch):
        fake_module = run_main(mock_genai, monkeypatch, {})

        fake_module.exit_json.assert_called_once()
        kwargs = fake_module.exit_json.call_args.kwargs
        assert kwargs["changed"] is False
        assert kwargs["total_tokens"] == 42
        assert kwargs["cached_content_token_count"] is None

    def test_cached_content_token_count_passthrough(self, mock_genai, monkeypatch):
        response = MagicMock()
        response.total_tokens = 100
        response.cached_content_token_count = 30
        fake_module = run_main(mock_genai, monkeypatch, {}, count_tokens_return=response)

        assert fake_module.exit_json.call_args.kwargs["cached_content_token_count"] == 30


class TestConfigBuilding:
    def test_no_config_object_created_when_no_optional_params(self, mock_genai, monkeypatch):
        run_main(mock_genai, monkeypatch, {})

        assert mock_genai.types.CountTokensConfig.call_args is None

    def test_system_instruction_and_tools_passed_through(self, mock_genai, monkeypatch):
        tools = [{"function_declarations": [{"name": "get_weather"}]}]
        run_main(mock_genai, monkeypatch, {"system_instruction": "Be terse.", "tools": tools})

        config_kwargs = mock_genai.types.CountTokensConfig.call_args.kwargs
        assert config_kwargs["system_instruction"] == "Be terse."
        assert config_kwargs["tools"] == tools
