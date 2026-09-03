#!/usr/bin/python
# Copyright: (c) 2026, Adam Knochowski (@aknochow)
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DOCUMENTATION = r"""
---
module: count_tokens
short_description: Count input tokens for a Gemini request without generating
description:
  - Calls C(client.models.count_tokens()) directly via the official google-genai Python SDK.
  - Useful as a pre-flight budget check before an expensive M(aknochow.gemini.generate) call.
version_added: "0.1.0"
author:
  - Adam Knochowski (@aknochow)
options:
  model:
    description:
      - Model identifier (e.g., V(gemini-3.6-flash), V(gemini-3.1-pro-preview)).
    type: str
    required: true
  contents:
    description:
      - Prompt content. May be a plain string or a list of content dicts, matching the SDK's own flexibility.
    type: raw
    required: true
  system_instruction:
    description:
      - System instruction string, if the real M(aknochow.gemini.generate) call would include one.
    type: str
  tools:
    description:
      - List of tool dicts, if the real M(aknochow.gemini.generate) call would include tools.
    type: list
    elements: dict
extends_documentation_fragment:
  - aknochow.gemini.auth
requirements:
  - "google-genai >= 1.0.0"
"""

EXAMPLES = r"""
- name: Estimate cost before generating
  aknochow.gemini.count_tokens:
    model: gemini-3.6-flash
    contents: "{{ large_prompt }}"
  register: estimate

- name: Skip the call if the prompt is too large
  aknochow.gemini.generate:
    model: gemini-3.6-flash
    max_output_tokens: 1024
    contents: "{{ large_prompt }}"
  when: estimate.total_tokens < 50000
"""

RETURN = r"""
total_tokens:
  description: Number of input tokens the request would consume.
  type: int
  returned: always
cached_content_token_count:
  description: Input tokens that would be served from cached content.
  type: int
  returned: always
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aknochow.gemini.plugins.module_utils.gemini_client import (
    PROVIDER_ARGSPEC,
    get_client,
)


def main():
    argument_spec = dict(
        model=dict(type="str", required=True),
        contents=dict(type="raw", required=True),
        system_instruction=dict(type="str"),
        tools=dict(type="list", elements="dict"),
    )
    argument_spec.update(PROVIDER_ARGSPEC)

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    client = get_client(module)

    from google.genai import types
    from google.genai.errors import APIError

    config_kwargs = {}
    for key in ("system_instruction", "tools"):
        value = module.params.get(key)
        if value is not None:
            config_kwargs[key] = value

    try:
        response = client.models.count_tokens(
            model=module.params["model"],
            contents=module.params["contents"],
            config=types.CountTokensConfig(**config_kwargs) if config_kwargs else None,
        )
        module.exit_json(
            changed=False,
            total_tokens=response.total_tokens,
            cached_content_token_count=response.cached_content_token_count,
        )
    except APIError as e:
        module.fail_json(msg=str(e))


if __name__ == "__main__":
    main()
