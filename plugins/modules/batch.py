#!/usr/bin/python
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

DOCUMENTATION = r"""
---
module: batch
short_description: Submit, poll, or cancel a Gemini batch job
description:
  - Wraps the google-genai Batches API (C(client.batches)) for bulk asynchronous C(generate_content) requests.
version_added: "0.2.0"
author:
  - Adam Knochowski (@aknochow)
options:
  name:
    description:
      - Resource name of an existing batch job (as returned in RV(name) from a previous submission).
      - Required for O(state=absent) and for polling an existing batch instead of submitting a new one.
    type: str
  model:
    description:
      - Model identifier for a new batch. Required when submitting (O(state=present) without O(name)).
    type: str
  requests:
    description:
      - List of per-request dicts submitted as inline batch requests, matching the SDK's own
        C(InlinedRequest) shape directly — each with C(contents) (required), and optionally
        C(model) (to override O(model) for that request), C(config) (a C(GenerateContentConfig)-style
        dict), and C(metadata) (a string-to-string dict echoed back on the matching result).
      - Required to submit a new batch when O(name) is not set.
    type: list
    elements: dict
  display_name:
    description:
      - Human-readable label for a new batch job.
    type: str
  wait:
    description:
      - If true, poll until the batch reaches a terminal state before returning.
    type: bool
    default: false
  wait_timeout:
    description:
      - Maximum time in seconds to wait when O(wait=true).
    type: int
    default: 600
  state:
    description:
      - Use V(present) to submit or poll a batch, V(absent) to cancel one.
    type: str
    choices: [present, absent]
    default: present
extends_documentation_fragment:
  - aknochow.gemini.auth
requirements:
  - "google-genai >= 1.0.0"
"""

EXAMPLES = r"""
- name: Submit a batch of requests
  aknochow.gemini.batch:
    model: gemini-3.6-flash
    requests:
      - contents: "Summarize {{ file1_content }}"
        metadata:
          source: file-1
      - contents: "Summarize {{ file2_content }}"
        metadata:
          source: file-2
  register: batch

- name: Poll until the batch finishes
  aknochow.gemini.batch:
    name: "{{ batch.name }}"
    wait: true
    wait_timeout: 1800
  register: finished

- name: Cancel a batch
  aknochow.gemini.batch:
    name: "{{ batch.name }}"
    state: absent
"""

RETURN = r"""
name:
  description: The batch job's resource name.
  type: str
  returned: always
state:
  description: Current job state (e.g. C(JOB_STATE_RUNNING), C(JOB_STATE_SUCCEEDED)).
  type: str
  returned: always
results:
  description: >-
    Per-request results, in the same order as O(requests), populated once the job reaches a
    terminal state and was built from inline requests.
  type: list
  returned: when the batch has reached a terminal state
  contains:
    metadata:
      description: The metadata dict echoed back from the matching request, if any.
      type: dict
    text:
      description: Concatenated text from the first candidate's parts, if the request succeeded.
      type: str
    response:
      description: Full raw response for this request, if it succeeded.
      type: dict
    error:
      description: Error encountered while processing this request, if it failed.
      type: str
"""

import time

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.aknochow.gemini.plugins.module_utils.gemini_client import (
    PROVIDER_ARGSPEC,
    get_client,
)

TERMINAL_STATES = frozenset(
    (
        "JOB_STATE_SUCCEEDED",
        "JOB_STATE_FAILED",
        "JOB_STATE_CANCELLED",
        "JOB_STATE_EXPIRED",
        "JOB_STATE_PARTIALLY_SUCCEEDED",
    )
)


def state_name(state):
    # Real SDK responses carry a JobState enum whose str() includes the
    # enum class name (e.g. "JobState.JOB_STATE_SUCCEEDED") -- .name (or
    # the plain string a test fixture sets directly) gives the bare
    # value this module's terminal-state check and return value both
    # need to compare/display correctly.
    return getattr(state, "name", state)


def flatten_result_entry(entry):
    response = entry.response
    candidate = response.candidates[0] if response and response.candidates else None
    parts = candidate.content.parts if candidate and candidate.content else []
    text = "".join(part.text for part in parts if part.text)
    return dict(
        metadata=entry.metadata,
        text=text,
        response=response.model_dump(mode="json") if response else None,
        error=str(entry.error) if entry.error else None,
    )


def flatten_batch(batch, changed):
    state = state_name(batch.state) if batch.state else None
    result = dict(changed=changed, name=batch.name, state=state)
    if state in TERMINAL_STATES and batch.dest and batch.dest.inlined_responses:
        result["results"] = [flatten_result_entry(entry) for entry in batch.dest.inlined_responses]
    return result


def main():
    argument_spec = dict(
        name=dict(type="str"),
        model=dict(type="str"),
        requests=dict(type="list", elements="dict"),
        display_name=dict(type="str"),
        wait=dict(type="bool", default=False),
        wait_timeout=dict(type="int", default=600),
        state=dict(type="str", choices=["present", "absent"], default="present"),
    )
    argument_spec.update(PROVIDER_ARGSPEC)

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=False,
    )

    client = get_client(module)

    from google.genai import types
    from google.genai.errors import APIError

    batch_name = module.params.get("name")
    desired_state = module.params["state"]

    try:
        if desired_state == "absent":
            if not batch_name:
                module.fail_json(msg="'name' is required when state=absent")
            client.batches.cancel(name=batch_name)
            # cancel() itself returns nothing -- re-fetch so the return
            # value reflects the batch's actual post-cancel state
            # instead of just echoing back the name the caller passed in.
            batch = client.batches.get(name=batch_name)
            module.exit_json(**flatten_batch(batch, changed=True))
            return

        if batch_name:
            batch = client.batches.get(name=batch_name)
            changed = False
        else:
            requests = module.params.get("requests")
            model = module.params.get("model")
            if not requests or not model:
                module.fail_json(
                    msg="'model' and 'requests' are required to submit a new batch when 'name' is not set"
                )
            config_kwargs = {}
            display_name = module.params.get("display_name")
            if display_name:
                config_kwargs["display_name"] = display_name
            batch = client.batches.create(
                model=model,
                src=requests,
                config=types.CreateBatchJobConfig(**config_kwargs) if config_kwargs else None,
            )
            changed = True

        if module.params.get("wait"):
            timeout = module.params.get("wait_timeout") or 600
            deadline = time.monotonic() + timeout
            while state_name(batch.state) not in TERMINAL_STATES:
                if time.monotonic() >= deadline:
                    module.fail_json(
                        msg=f"Timed out waiting for batch {batch.name} to finish "
                        f"(state={state_name(batch.state)})"
                    )
                time.sleep(5)
                batch = client.batches.get(name=batch.name)

        module.exit_json(**flatten_batch(batch, changed))
    except APIError as e:
        module.fail_json(msg=str(e))


if __name__ == "__main__":
    main()
