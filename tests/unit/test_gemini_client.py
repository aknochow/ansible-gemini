# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock


class TestProviderArgspec:
    def test_backend_default(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.module_utils.gemini_client import (
            PROVIDER_ARGSPEC,
        )

        assert PROVIDER_ARGSPEC["backend"]["default"] == "api"
        assert PROVIDER_ARGSPEC["backend"]["choices"] == ["api", "vertex"]

    def test_api_key_is_no_log(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.module_utils.gemini_client import (
            PROVIDER_ARGSPEC,
        )

        assert PROVIDER_ARGSPEC["api_key"]["no_log"] is True


class TestGetClient:
    def test_api_backend(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.module_utils.gemini_client import (
            get_client,
        )

        module = MagicMock()
        module.params = {
            "backend": "api",
            "api_key": "test-key",
            "project_id": None,
            "location": None,
            "timeout": None,
            "max_retries": None,
        }

        get_client(module)
        mock_genai.Client.assert_called_once()
        call_kwargs = mock_genai.Client.call_args.kwargs
        assert call_kwargs["api_key"] == "test-key"

    def test_api_backend_requires_api_key(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.module_utils.gemini_client import (
            get_client,
        )

        module = MagicMock()
        module.params = {
            "backend": "api",
            "api_key": None,
            "project_id": None,
            "location": None,
        }

        get_client(module)
        module.fail_json.assert_called_once()
        assert "api_key" in module.fail_json.call_args.kwargs["msg"]
        # Regression test: get_client() must return immediately after
        # fail_json() rather than falling through to
        # genai.Client(api_key=None). A bare MagicMock()'s fail_json()
        # doesn't raise/exit the way the real AnsibleModule.fail_json()
        # does, so without an explicit `return` right after the call,
        # this assertion is what actually catches the fallthrough --
        # fails on the unfixed code, passes once get_client() returns
        # early.
        mock_genai.Client.assert_not_called()

    def test_vertex_backend(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.module_utils.gemini_client import (
            get_client,
        )

        module = MagicMock()
        module.params = {
            "backend": "vertex",
            "api_key": None,
            "project_id": "my-project",
            "location": "us-east5",
        }

        get_client(module)
        mock_genai.Client.assert_called_once()
        call_kwargs = mock_genai.Client.call_args.kwargs
        assert call_kwargs["vertexai"] is True
        assert call_kwargs["project"] == "my-project"
        assert call_kwargs["location"] == "us-east5"

    def test_vertex_backend_requires_project_and_location(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.module_utils.gemini_client import (
            get_client,
        )

        module = MagicMock()
        module.params = {
            "backend": "vertex",
            "api_key": None,
            "project_id": None,
            "location": None,
        }

        get_client(module)
        module.fail_json.assert_called_once()
        # Same regression coverage as test_api_backend_requires_api_key
        # above -- without the fix, this falls through to
        # genai.Client(vertexai=True, project=None, location=None).
        mock_genai.Client.assert_not_called()

    def test_unknown_backend(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.module_utils.gemini_client import (
            get_client,
        )

        module = MagicMock()
        module.params = {
            "backend": "carrier-pigeon",
            "api_key": None,
            "project_id": None,
            "location": None,
        }

        get_client(module)
        module.fail_json.assert_called_once()
        assert "Unknown backend" in module.fail_json.call_args.kwargs["msg"]


class TestHttpOptions:
    def test_defaults_build_120s_timeout_and_3_total_attempts(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.module_utils.gemini_client import (
            get_client,
        )

        module = MagicMock()
        module.params = {
            "backend": "api",
            "api_key": "test-key",
            "project_id": None,
            "location": None,
            "timeout": None,
            "max_retries": None,
        }

        get_client(module)

        # HttpOptions.timeout is milliseconds; 120.0s default -> 120000.
        assert mock_genai.types.HttpOptions.call_args.kwargs["timeout"] == 120000
        # attempts counts the original request too, unlike Anthropic's
        # max_retries (retries only) -- default max_retries=2 -> 3 total.
        assert mock_genai.types.HttpRetryOptions.call_args.kwargs["attempts"] == 3

    def test_custom_timeout_and_max_retries_are_converted(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.module_utils.gemini_client import (
            get_client,
        )

        module = MagicMock()
        module.params = {
            "backend": "api",
            "api_key": "test-key",
            "project_id": None,
            "location": None,
            "timeout": 5.5,
            "max_retries": 0,
        }

        get_client(module)

        assert mock_genai.types.HttpOptions.call_args.kwargs["timeout"] == 5500
        assert mock_genai.types.HttpRetryOptions.call_args.kwargs["attempts"] == 1

    def test_http_options_passed_to_client_for_both_backends(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.module_utils.gemini_client import (
            get_client,
        )

        http_options_sentinel = mock_genai.types.HttpOptions.return_value

        api_module = MagicMock()
        api_module.params = {
            "backend": "api",
            "api_key": "test-key",
            "project_id": None,
            "location": None,
            "timeout": None,
            "max_retries": None,
        }
        get_client(api_module)
        assert mock_genai.Client.call_args.kwargs["http_options"] is http_options_sentinel

        vertex_module = MagicMock()
        vertex_module.params = {
            "backend": "vertex",
            "api_key": None,
            "project_id": "my-project",
            "location": "us-east5",
            "timeout": None,
            "max_retries": None,
        }
        get_client(vertex_module)
        assert mock_genai.Client.call_args.kwargs["http_options"] is http_options_sentinel
