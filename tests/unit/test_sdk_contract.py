# SPDX-License-Identifier: Apache-2.0

"""Lock the google-genai surface aknochow.gemini actually calls.

The unit conftest mocks google.genai. This test drops that mock and
imports the installed SDK.
"""

from __future__ import annotations

import inspect
import sys
from importlib.metadata import version

from packaging.version import Version


def _import_real_genai():
    saved_modules = {
        key: module
        for key, module in sys.modules.items()
        if key == "google" or key.startswith("google.")
    }
    try:
        for key in saved_modules:
            sys.modules.pop(key, None)
        from google import genai
        from google.genai import types
        from google.genai.errors import APIError

        return genai, types, APIError
    finally:
        for key in list(sys.modules):
            if key == "google" or key.startswith("google."):
                sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


def test_installed_sdk_meets_the_collection_floor():
    assert Version(version("google-genai")) >= Version("2.27.0")


def test_client_http_options_and_model_methods_exist():
    genai, types, api_error = _import_real_genai()
    http_options = types.HttpOptions(timeout=1000, retry_options=types.HttpRetryOptions(attempts=2))
    assert http_options.timeout == 1000
    assert callable(genai.Client)
    assert issubclass(api_error, Exception)
    params = inspect.signature(genai.Client).parameters
    for name in ("api_key", "http_options"):
        assert name in params
        assert params[name].kind is not inspect.Parameter.POSITIONAL_ONLY
