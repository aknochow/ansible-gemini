#!/usr/bin/python
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

DOCUMENTATION = r"""
---
module: generate
short_description: Generate content with Gemini and return the response
description:
  - Calls C(client.models.generate_content()) directly via the official google-genai Python SDK.
  - Returns both the raw response and flattened convenience fields for use with O(register).
version_added: "0.1.0"
author:
  - Adam Knochowski (@aknochow)
options:
  model:
    description:
      - Model identifier (e.g., V(gemini-3.5-flash), V(gemini-3-pro)).
    type: str
    required: true
  contents:
    description:
      - Prompt content. May be a plain string or a list of content dicts, matching the SDK's own flexibility.
    type: raw
    required: true
  max_output_tokens:
    description:
      - Maximum number of tokens to generate. There is no default — an explicit
        budget must be chosen for every call.
    type: int
    required: true
  system_instruction:
    description:
      - System instruction string.
    type: str
  temperature:
    description:
      - Sampling temperature.
    type: float
  top_p:
    description:
      - Nucleus sampling parameter.
    type: float
  top_k:
    description:
      - Top-k sampling parameter.
    type: int
  stop_sequences:
    description:
      - List of strings that stop generation when encountered.
    type: list
    elements: str
extends_documentation_fragment:
  - aknochow.gemini.auth
requirements:
  - "google-genai >= 1.0.0"
"""

EXAMPLES = r"""
- name: Basic generation
  aknochow.gemini.generate:
    model: gemini-3.5-flash
    max_output_tokens: 512
    contents: "Summarize this changelog in one sentence: {{ changelog }}"
  register: result

- name: Generate with a system instruction
  aknochow.gemini.generate:
    model: gemini-3.5-flash
    max_output_tokens: 512
    system_instruction: "Answer in a single word."
    contents: "What color is the sky?"
  register: result

- name: Call via Vertex AI
  aknochow.gemini.generate:
    backend: vertex
    project_id: my-gcp-project
    location: us-east5
    model: gemini-3.5-flash
    max_output_tokens: 512
    contents: "Hello"
"""

RETURN = r"""
response:
  description: Full raw response from generate_content().
  type: dict
  returned: always
text:
  description: Concatenated text from the first candidate's parts.
  type: str
  returned: always
finish_reason:
  description: Why generation stopped.
  type: str
  returned: always
usage:
  description: Token usage for the request.
  type: dict
  returned: always
  contains:
    prompt_token_count:
      description: Number of input tokens billed for this request.
      type: int
    candidates_token_count:
      description: Number of output tokens generated.
      type: int
    total_token_count:
      description: Total tokens billed for this request.
      type: int
    cached_content_token_count:
      description: Input tokens served from cached content.
      type: int
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.aknochow.gemini.plugins.module_utils.gemini_client import (
    PROVIDER_ARGSPEC,
    get_client,
)


def flatten_response(response):
    candidate = response.candidates[0] if response.candidates else None
    parts = candidate.content.parts if candidate and candidate.content else []
    text = "".join(part.text for part in parts if part.text)

    usage = response.usage_metadata
    result = dict(
        response=response.model_dump(mode="json"),
        text=text,
        finish_reason=str(candidate.finish_reason) if candidate and candidate.finish_reason else None,
        usage=dict(
            prompt_token_count=usage.prompt_token_count,
            candidates_token_count=usage.candidates_token_count,
            total_token_count=usage.total_token_count,
            cached_content_token_count=usage.cached_content_token_count,
        )
        if usage
        else None,
    )
    return result


def main():
    argument_spec = dict(
        model=dict(type="str", required=True),
        contents=dict(type="raw", required=True),
        max_output_tokens=dict(type="int", required=True),
        system_instruction=dict(type="str"),
        temperature=dict(type="float"),
        top_p=dict(type="float"),
        top_k=dict(type="int"),
        stop_sequences=dict(type="list", elements="str"),
    )
    argument_spec.update(PROVIDER_ARGSPEC)

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=False,
    )

    client = get_client(module)

    from google.genai import types
    from google.genai.errors import APIError

    config_kwargs = dict(max_output_tokens=module.params["max_output_tokens"])
    for key in ("system_instruction", "temperature", "top_p", "top_k", "stop_sequences"):
        value = module.params.get(key)
        if value is not None:
            config_kwargs[key] = value

    try:
        response = client.models.generate_content(
            model=module.params["model"],
            contents=module.params["contents"],
            config=types.GenerateContentConfig(**config_kwargs),
        )
        module.exit_json(changed=True, **flatten_response(response))
    except APIError as e:
        module.fail_json(msg=str(e))


if __name__ == "__main__":
    main()
