# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations


class ModuleDocFragment:

    DOCUMENTATION = r"""
options:
  backend:
    description:
      - Which google-genai client backend to use.
      - If the value is not specified, the value of the E(ANSIBLE_GEMINI_BACKEND) environment variable will be used.
    type: str
    choices: [api, vertex]
    default: api
  api_key:
    description:
      - API key for the direct Gemini API.
      - Required when O(backend=api).
      - If the value is not specified, the value of the E(GEMINI_API_KEY) or E(GOOGLE_API_KEY) environment variable will be used.
    type: str
  project_id:
    description:
      - Google Cloud project ID for Vertex AI.
      - Required when O(backend=vertex).
      - If the value is not specified, the value of the E(GOOGLE_CLOUD_PROJECT) environment variable will be used.
    type: str
  location:
    description:
      - Google Cloud location/region for Vertex AI.
      - Required when O(backend=vertex).
      - If the value is not specified, the value of the E(GOOGLE_CLOUD_LOCATION) environment variable will be used.
    type: str
"""
