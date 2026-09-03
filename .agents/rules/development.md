---
trigger: always_on
---

# Development & Operational Guidelines for aknochow.gemini

## Security & Secrets
- Never print or echo raw secret environment variables (e.g. `GEMINI_API_KEY`, API tokens) in command output. Use safe presence/length checks or test credentials by invoking non-leaking tools/playbooks.

## Local Environment & Tooling
- Always activate the local virtual environment before running python, pytest, or ansible commands:
  ```bash
  source .venv/bin/activate
  ```
- After making edits to any module in `plugins/`, reinstall the collection locally:
  ```bash
  ansible-galaxy collection install . --force
  ```

## Gemini API & Thinking Configuration
- When invoking the Gemini Developer API (`backend: api`), do not pass `thinking_config` if `thinking_budget` is 0 and `thinking_level` is not set. The API rejects a budget of 0 with `400 INVALID_ARGUMENT`.
- Reasoning effort can be configured via `effort` (or `thinking_level`: `minimal`, `low`, `medium`, `high`) or `thinking_budget` (int).
- Supported verified models on `backend: api` include `gemini-3.7-flash` (default), `gemini-3.6-flash`, and `gemini-3.5-flash`.
