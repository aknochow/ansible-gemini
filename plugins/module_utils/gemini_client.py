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
)


def get_client(module: AnsibleModule):
    """Construct the right google-genai Client for module.params['backend']."""
    backend = module.params["backend"]

    try:
        from google import genai
    except ImportError:
        module.fail_json(
            msg="The google-genai Python SDK is required. Install it with: pip install google-genai"
        )
        return

    if backend == "api":
        api_key = module.params.get("api_key")
        if not api_key:
            module.fail_json(msg="'api_key' is required when backend=api")
            return
        return genai.Client(api_key=api_key)

    if backend == "vertex":
        project_id = module.params.get("project_id")
        location = module.params.get("location")
        if not project_id or not location:
            module.fail_json(
                msg="'project_id' and 'location' are required when backend=vertex"
            )
            return
        return genai.Client(vertexai=True, project=project_id, location=location)

    module.fail_json(msg=f"Unknown backend: {backend}")
    return
