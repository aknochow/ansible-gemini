# aknochow.gemini

Ansible collection for calling Google's Gemini models directly via the
official [google-genai Python SDK](https://github.com/googleapis/python-genai)
— not a CLI wrapper. Built for deterministic, structured invocation from
Ansible tasks (`register`, `set_fact`, `when`, loops), the same shape as its
companion collection [`aknochow.claude`](https://github.com/aknochow/ansible-claude).

## Why this exists

The motivating idea is model-cost tiering for multi-agent Ansible
pipelines: Gemini Flash as a candidate middle tier between cheaper and
pricier models, so individual pipeline stages can route to whichever
model/vendor fits that stage's difficulty and budget. That's a hypothesis,
not a measured result yet — no specific cost-savings numbers are claimed
here until a real usage/pricing comparison has been run.

**Recommended default model: `gemini-3.6-flash`.** It replaced
`gemini-3.5-flash` on July 21, 2026 at the same input price with a 17%
output-price cut ($7.50 vs. $9.00 per million output tokens) and a
slightly better benchmark score — see `examples/model_comparison.yml`
for a live cost/correctness comparison across the current 3.x lineup.

## Modules

| Module | Purpose |
|---|---|
| `generate` | Call `generate_content()` — flattened text/usage return values |

Structured output (`response_schema`/`response_mime_type`) and function
calling (`tools`/`tool_config`) are supported — see below. A
batch-equivalent module is not yet; that's tracked as follow-up work.

## Requirements

```
pip install 'google-genai>=1.0.0'
```

## Auth

Set `backend` to `api` (default) or `vertex`. Each mode's credentials can
be passed as module params or via environment variables — see the
module's documentation (`ansible-doc aknochow.gemini.generate`) for the
full list.

```bash
export GEMINI_API_KEY=...
# or, for Vertex:
export ANSIBLE_GEMINI_BACKEND=vertex
export GOOGLE_CLOUD_PROJECT=my-gcp-project
export GOOGLE_CLOUD_LOCATION=us-east5
```

### `generate` — basic call

```yaml
- name: Basic generation
  aknochow.gemini.generate:
    model: gemini-3.6-flash
    max_output_tokens: 512
    contents: "Summarize this changelog in one sentence: {{ changelog }}"
  register: result
# result.text, result.usage.{prompt_token_count,candidates_token_count,...}
```

### Vertex AI

```yaml
- aknochow.gemini.generate:
    backend: vertex
    project_id: my-gcp-project
    location: us-east5
    model: gemini-3.6-flash
    max_output_tokens: 512
    contents: "Hello"
```

Newer models (e.g. `gemini-3.6-flash`) may only be servable via
`location: global` on a given project even though `models.list()` shows
them as available — if you get a `404 NOT_FOUND` on a region you'd expect
to work, try `global` first.

See `examples/basic_generate.yml` for a runnable playbook, and
`examples/model_comparison.yml` to compare Gemini 3.x models against each
other on correctness/tokens/cost (see below).

### Structured output

```yaml
- name: Extract structured fields from free text
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
# result.structured.name, result.structured.severity
```

`response_schema` is a plain JSON Schema dict — the SDK parses the model's
JSON response against it and returns the parsed value as `result.structured`
(only present when `response_schema` is set). `response_mime_type` defaults
to `application/json` automatically once `response_schema` is set; only
override it if you need `text/plain` for some other reason.

See `examples/structured_output.yml` for a runnable playbook.

### Function calling

```yaml
- name: Ask a question that requires calling get_weather
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
# result.tool_calls -> [{id, name, args}, ...]
```

`tools` and `tool_config` are passed straight through to the SDK's own
`Tool`/`ToolConfig` shapes — no reshaping, so anything the SDK itself
accepts there (including built-in tools like `google_search` or
`code_execution`) works too. Function calls the model makes come back as
`result.tool_calls`, each with `id`, `name`, and `args` (a dict) — this
module doesn't manage multi-turn conversation state itself; feed a
function's result back via `contents` on a follow-up call the same way
you'd construct any other multi-turn `contents` list.

See `examples/function_calling.yml` for a runnable playbook.

### Thinking models and `max_output_tokens`

Thinking-capable models (e.g. `gemini-3.5-flash`, `gemini-3.6-flash`) spend
part of `max_output_tokens` on internal reasoning ("thoughts") that's never
returned in `text` — by default, `thinking_budget` is `0`, disabling
thinking so `max_output_tokens` is a fully deterministic budget for
visible output only. If you raise `thinking_budget` above 0, budget
accordingly: a low `max_output_tokens` combined with a nonzero thinking
budget can burn the whole budget on thinking and return `finish_reason:
MAX_TOKENS` with truncated or empty `text` (confirmed live against both
`gemini-3.5-flash` and `gemini-3.6-flash` during development — see
`result.usage.thoughts_token_count`).

## Testing

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install ansible-core pytest
ansible-galaxy collection install . --force
python -m pytest tests/unit/
```

Unit tests mock the `google-genai` SDK — no network access or real
credentials required. Live-verified against Vertex AI (`gemini-3.6-flash`
and `gemini-3.5-flash`, `backend: vertex`, `location: global`) during
development, including the `thinking_budget` truncation gotcha above.
Live verification against the direct Gemini API (`backend: api`) and a
broader model/quota survey remain open follow-up work.

### Live model smoke test

`tests/test_models.yml` calls `generate` against each of the newest
Gemini 3.x text models (`gemini-3-flash-preview`, `gemini-3.1-pro-preview`,
`gemini-3.1-flash-lite`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`,
`gemini-3.6-flash`) with the same prompt and reports pass/fail per model —
useful after a model list changes or a new preview lands:

```bash
ansible-playbook tests/test_models.yml \
  -e vertex_project=your-gcp-project-id -e vertex_location=global
```

All 6 confirmed working during development against a Vertex AI project
with Gemini models enabled. Excludes the 3.x image-generation variants
(`gemini-3.1-flash-image`, `gemini-3-pro-image`, etc.) since those return a
different response shape than plain text generation.

### Model comparison example

`examples/model_comparison.yml` runs the same math/sentiment/reasoning
tasks across all 6 models and reports correctness, token usage, and an
estimated cost per model (pricing table sourced and cross-checked
2026-07-27 — preview models' pricing is less certain since it isn't yet
on Google's own pricing page and may change before GA). Live-run during
development: all 6 models answered both deterministic tasks correctly;
`gemini-3.1-flash-lite` was cheapest and `gemini-3.1-pro-preview` priciest
for that particular task mix — token/pricing differences will vary by
workload, this isn't a general "always use X" conclusion.

```bash
ansible-playbook examples/model_comparison.yml \
  -e vertex_project=your-gcp-project-id -e vertex_location=global
```
