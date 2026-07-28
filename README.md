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

## Modules

| Module | Purpose |
|---|---|
| `generate` | Call `generate_content()` — flattened text/usage return values |

This is a first, deliberately minimal slice: no structured output, tool
use/function calling, or a batch-equivalent module yet. Those are tracked
as follow-up work.

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
    model: gemini-3.5-flash
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
    model: gemini-3.5-flash
    max_output_tokens: 512
    contents: "Hello"
```

See `examples/basic_generate.yml` for a runnable playbook.

## Testing

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install ansible-core pytest
ansible-galaxy collection install . --force
python -m pytest tests/unit/
```

Unit tests mock the `google-genai` SDK — no network access or real
credentials required. Live verification against a real API key/Vertex
project (and confirming which Gemini models are actually enabled/quota'd
there) is still open follow-up work.
