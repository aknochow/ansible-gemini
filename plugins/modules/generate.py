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
      - Model identifier (e.g., V(gemini-3.6-flash), V(gemini-3.1-pro-preview)).
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
  thinking_budget:
    description:
      - Token budget for internal "thinking" on thinking-capable models (e.g. gemini-3.6-flash, gemini-3.7-flash).
      - Defaults to V(0), meaning "thinking disabled" so O(max_output_tokens) is a deterministic
        budget for visible output only — on thinking-capable models, a nonzero default would
        silently consume part of O(max_output_tokens) on internal reasoning never returned to the
        caller, and could exhaust the whole budget before any visible text is generated
        (I(finish_reason)=C(MAX_TOKENS) with empty/truncated I(text)). Raise this if you want the
        model to reason before answering.
      - This determinism guarantee only holds on O(backend)=V(vertex), where an explicit
        C(ThinkingConfig(thinking_budget=0)) is sent and genuinely disables thinking. On
        O(backend)=V(api) (the Gemini Developer API), the same explicit C(thinking_budget=0) is
        REJECTED by the API with C(400 INVALID_ARGUMENT), so a budget of V(0) on that backend sends
        no C(thinking_config) at all and the model's own default thinking behavior applies instead.
        That default has been observed ON for at least one thinking-capable model
        (C(gemini-3.6-flash) returned a nonzero I(thoughts_token_count) with no C(thinking_config)
        sent, verified live against the Developer API on 2026-08-24). On O(backend)=V(api) the
        V(0) default therefore does NOT guarantee thinking is disabled and O(max_output_tokens) may
        still be partly consumed by unreturned thinking tokens; callers who need a strict
        visible-output-only budget on that backend should account for this, or use
        O(backend)=V(vertex) where the explicit disable is honored.
    type: int
    default: 0
  thinking_level:
    description:
      - Reasoning effort level on thinking-capable models (e.g. gemini-3.7-flash).
      - Choices are V(minimal), V(low), V(medium), or V(high).
      - Can be combined with or used instead of O(thinking_budget).
    type: str
    choices: [minimal, low, medium, high]
    aliases: [effort, effort_level]
  response_schema:
    description:
      - 'JSON Schema-style dict describing the required shape of the response, e.g. C({"type": "object", "properties": {...}}).'
      - When set, the response text is parsed as JSON into the RV(structured) return value.
      - If O(response_mime_type) is not also set, it defaults to V(application/json).
    type: dict
  response_mime_type:
    description:
      - Output MIME type of the generated candidate text.
      - Required to be V(application/json) for O(response_schema) to take effect.
    type: str
    choices: [text/plain, application/json]
  tools:
    description:
      - 'List of tool dicts, matching the SDK''s own C(Tool) shape directly, e.g. C({"function_declarations": [{"name": ..., "description": ..., "parameters": {...}}]}).'
      - Function calls the model makes are returned in the RV(tool_calls) return value.
    type: list
    elements: dict
  tool_config:
    description:
      - 'Tool-calling behavior, matching the SDK''s own C(ToolConfig) shape directly, e.g. C({"function_calling_config": {"mode": "ANY", "allowed_function_names": [...]}}).'
    type: dict
  labels:
    description:
      - 'User-defined string-to-string metadata to break down billed charges by, e.g. C({"team": "platform", "pipeline": "review"}).'
    type: dict
extends_documentation_fragment:
  - aknochow.gemini.auth
requirements:
  - "google-genai >= 1.0.0"
"""

EXAMPLES = r"""
- name: Basic generation
  aknochow.gemini.generate:
    model: gemini-3.6-flash
    max_output_tokens: 512
    contents: "Summarize this changelog in one sentence: {{ changelog }}"
  register: result

- name: Generate with a system instruction
  aknochow.gemini.generate:
    model: gemini-3.6-flash
    max_output_tokens: 512
    system_instruction: "Answer in a single word."
    contents: "What color is the sky?"
  register: result

- name: Structured extraction with response_schema
  aknochow.gemini.generate:
    model: gemini-3.6-flash
    max_output_tokens: 1024
    contents: "Extract the name and severity from this bug report: {{ bug_text }}"
    response_schema:
      type: object
      properties:
        name: {type: string}
        severity: {type: string, enum: [low, medium, high, critical]}
      required: [name, severity]
  register: result

- name: Use structured result directly
  ansible.builtin.debug:
    msg: "{{ result.structured.name }} is {{ result.structured.severity }}"

- name: Function calling with tools/tool_config
  aknochow.gemini.generate:
    model: gemini-3.6-flash
    max_output_tokens: 512
    contents: "What's the weather in Boston?"
    tools:
      - function_declarations:
          - name: get_weather
            description: Get the current weather for a location
            parameters:
              type: object
              properties:
                location: {type: string}
              required: [location]
    tool_config:
      function_calling_config:
        mode: ANY
  register: result

- name: Act on the model's function call
  ansible.builtin.debug:
    msg: "Model wants to call {{ item.name }} with {{ item.args }}"
  loop: "{{ result.tool_calls }}"

- name: Call via Vertex AI
  aknochow.gemini.generate:
    backend: vertex
    project_id: my-gcp-project
    location: us-east5
    model: gemini-3.6-flash
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
tool_calls:
  description: List of function calls the model made, each with C(id), C(name), and C(args).
  type: list
  returned: always
structured:
  description: Parsed JSON value when O(response_schema) requested structured output.
  type: raw
  returned: when response_schema is set
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
    thoughts_token_count:
      description: Tokens spent on internal thinking (nonzero only if O(thinking_budget) was raised above 0).
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
    tool_calls = [
        dict(id=part.function_call.id, name=part.function_call.name, args=part.function_call.args)
        for part in parts
        if part.function_call
    ]

    usage = response.usage_metadata
    result = dict(
        response=response.model_dump(mode="json"),
        text=text,
        finish_reason=str(candidate.finish_reason) if candidate and candidate.finish_reason else None,
        tool_calls=tool_calls,
        usage=dict(
            prompt_token_count=usage.prompt_token_count,
            candidates_token_count=usage.candidates_token_count,
            total_token_count=usage.total_token_count,
            cached_content_token_count=usage.cached_content_token_count,
            thoughts_token_count=usage.thoughts_token_count,
        )
        if usage
        else None,
    )
    # The SDK itself only populates .parsed when response_schema was passed
    # in the request config, so this naturally matches the RETURN doc's
    # "returned: when response_schema is set" -- no extra request-side flag
    # needed to gate it (unlike aknochow.claude's message.py, whose SDK has
    # no equivalent and must re-parse text manually behind an explicit gate).
    if response.parsed is not None:
        result["structured"] = response.parsed
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
        thinking_budget=dict(type="int", default=0),
        thinking_level=dict(
            type="str",
            choices=["minimal", "low", "medium", "high"],
            aliases=["effort", "effort_level"],
        ),
        response_schema=dict(type="dict"),
        response_mime_type=dict(type="str", choices=["text/plain", "application/json"]),
        tools=dict(type="list", elements="dict"),
        tool_config=dict(type="dict"),
        labels=dict(type="dict"),
    )
    argument_spec.update(PROVIDER_ARGSPEC)

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=False,
    )

    client = get_client(module)

    from google.genai import types
    from google.genai.errors import APIError

    config_kwargs = dict(
        max_output_tokens=module.params["max_output_tokens"],
    )
    # The Developer API (backend=api) rejects an explicit
    # ThinkingConfig(thinking_budget=0) with 400 INVALID_ARGUMENT, so a
    # budget of 0 must omit thinking_config entirely on that backend --
    # verified live 2026-08-24: gemini-3.6-flash on backend=api returned a
    # nonzero thoughts_token_count with no thinking_config sent at all, so
    # this is a real limitation, not just an API quirk to work around
    # silently. See thinking_budget's DOCUMENTATION for the consequence.
    #
    # Vertex AI (backend=vertex) has no such restriction and DOES honor an
    # explicit thinking_budget=0 to disable thinking, so send it there
    # unconditionally to preserve the deterministic-output-budget guarantee.
    thinking_kwargs = {}
    backend = module.params["backend"]
    if backend == "vertex":
        thinking_kwargs["thinking_budget"] = module.params["thinking_budget"]
    elif module.params["thinking_budget"] > 0:
        thinking_kwargs["thinking_budget"] = module.params["thinking_budget"]
    if module.params.get("thinking_level"):
        thinking_kwargs["thinking_level"] = module.params["thinking_level"]
    if thinking_kwargs:
        config_kwargs["thinking_config"] = types.ThinkingConfig(**thinking_kwargs)
    optional_keys = (
        "system_instruction",
        "temperature",
        "top_p",
        "top_k",
        "stop_sequences",
        "response_schema",
        "response_mime_type",
        "tools",
        "tool_config",
        "labels",
    )
    for key in optional_keys:
        value = module.params.get(key)
        if value is not None:
            config_kwargs[key] = value

    # response_schema requires a compatible response_mime_type; default it
    # to application/json rather than making every schema-only caller repeat
    # a second parameter the SDK can only meaningfully be application/json.
    if module.params.get("response_schema") is not None and "response_mime_type" not in config_kwargs:
        config_kwargs["response_mime_type"] = "application/json"

    try:
        response = client.models.generate_content(
            model=module.params["model"],
            contents=module.params["contents"],
            config=types.GenerateContentConfig(**config_kwargs),
        )
        # A generate_content call never mutates infrastructure state --
        # it's a query, same as the aknochow.claude message module.
        # changed is always False here, not conditional on the response.
        module.exit_json(changed=False, **flatten_response(response))
    except APIError as e:
        module.fail_json(msg=str(e))


if __name__ == "__main__":
    main()
