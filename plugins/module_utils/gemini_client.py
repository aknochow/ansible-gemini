# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule, env_fallback

PROVIDER_ARGSPEC = dict(
    backend=dict(
        type="str",
        choices=["api", "vertex"],
        default="api",
        fallback=(env_fallback, ["ANSIBLE_GEMINI_BACKEND"]),
    ),
    # Direct Gemini API
    api_key=dict(
        type="str",
        no_log=True,
        fallback=(env_fallback, ["GEMINI_API_KEY", "GOOGLE_API_KEY"]),
    ),
    # Vertex AI
    project_id=dict(
        type="str",
        fallback=(env_fallback, ["GOOGLE_CLOUD_PROJECT"]),
    ),
    location=dict(
        type="str",
        fallback=(env_fallback, ["GOOGLE_CLOUD_LOCATION"]),
    ),
    # Common
    timeout=dict(type="float", default=120.0),
    max_retries=dict(type="int", default=2),
)


def get_client(module: AnsibleModule):
    """Construct the right google-genai Client for module.params['backend']."""
    backend = module.params["backend"]

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        module.fail_json(
            msg="The google-genai Python SDK is required. Install it with: pip install google-genai"
        )
        return

    timeout = module.params.get("timeout") or 120.0
    max_retries = module.params.get("max_retries")
    if max_retries is None:
        max_retries = 2
    # HttpOptions.timeout is milliseconds, not seconds -- convert so this
    # module's own timeout param stays in the same units as
    # aknochow.claude's. retry_options.attempts counts the original
    # request too (unlike Anthropic's max_retries, which counts only
    # retries after it), so +1 keeps max_retries's meaning consistent
    # across both collections instead of leaking the SDK's own quirk.
    http_options = types.HttpOptions(
        timeout=int(timeout * 1000),
        retry_options=types.HttpRetryOptions(attempts=max_retries + 1),
    )

    if backend == "api":
        api_key = module.params.get("api_key")
        if not api_key:
            module.fail_json(msg="'api_key' is required when backend=api")
            return
        return genai.Client(api_key=api_key, http_options=http_options)

    if backend == "vertex":
        project_id = module.params.get("project_id")
        location = module.params.get("location")
        if not project_id or not location:
            module.fail_json(
                msg="'project_id' and 'location' are required when backend=vertex"
            )
            return
        return genai.Client(
            vertexai=True, project=project_id, location=location, http_options=http_options
        )

    module.fail_json(msg=f"Unknown backend: {backend}")
    return
