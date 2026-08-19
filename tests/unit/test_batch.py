# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def make_batch(name="batches/abc123", state="JOB_STATE_RUNNING", dest=None):
    batch = MagicMock()
    batch.name = name
    # Mirror the real SDK's enum-with-.name shape so state_name()'s
    # getattr(state, "name", state) exercises the same path as production.
    state_obj = MagicMock()
    state_obj.name = state
    batch.state = state_obj
    batch.dest = dest
    return batch


def make_dest(entries):
    dest = MagicMock()
    dest.inlined_responses = entries
    return dest


def make_result_entry(metadata=None, text="hi", error=None):
    entry = MagicMock()
    entry.metadata = metadata
    if error is not None:
        entry.response = None
        entry.error = error
    else:
        part = MagicMock()
        part.text = text
        candidate = MagicMock()
        candidate.content.parts = [part]
        response = MagicMock()
        response.candidates = [candidate]
        response.model_dump.return_value = {"raw": True}
        entry.response = response
        entry.error = None
    return entry


DEFAULT_MODULE_PARAMS = {
    "name": None,
    "model": None,
    "requests": None,
    "display_name": None,
    "wait": False,
    "wait_timeout": 600,
    "state": "present",
    "backend": "api",
    "api_key": "test-key",
    "project_id": None,
    "location": None,
}


def make_fake_module(params_overrides, fails=False):
    fake_module = MagicMock()
    fake_module.params = dict(DEFAULT_MODULE_PARAMS)
    fake_module.params.update(params_overrides)
    if fails:
        # Real AnsibleModule.fail_json() terminates the process -- without
        # this, main() would keep running past a validation failure during
        # tests and hit unrelated code with unset params.
        fake_module.fail_json.side_effect = SystemExit(1)
    return fake_module


class TestStateName:
    def test_enum_like_object_uses_name_attribute(self):
        from ansible_collections.aknochow.gemini.plugins.modules.batch import state_name

        state_obj = MagicMock()
        state_obj.name = "JOB_STATE_SUCCEEDED"
        assert state_name(state_obj) == "JOB_STATE_SUCCEEDED"

    def test_plain_string_passthrough(self):
        from ansible_collections.aknochow.gemini.plugins.modules.batch import state_name

        assert state_name("JOB_STATE_RUNNING") == "JOB_STATE_RUNNING"


class TestFlattenResultEntry:
    def test_successful_entry(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.modules.batch import flatten_result_entry

        entry = make_result_entry(metadata={"source": "file-1"}, text="hello")
        result = flatten_result_entry(entry)

        assert result["metadata"] == {"source": "file-1"}
        assert result["text"] == "hello"
        assert result["response"] == {"raw": True}
        assert result["error"] is None

    def test_failed_entry(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.modules.batch import flatten_result_entry

        entry = make_result_entry(metadata=None, error="boom")
        result = flatten_result_entry(entry)

        assert result["response"] is None
        assert result["error"] == "boom"
        assert result["text"] == ""


class TestFlattenBatch:
    def test_non_terminal_state_has_no_results_key(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.modules.batch import flatten_batch

        batch = make_batch(state="JOB_STATE_RUNNING")
        result = flatten_batch(batch, changed=True)

        assert result == {"changed": True, "name": "batches/abc123", "state": "JOB_STATE_RUNNING"}

    def test_terminal_state_with_dest_includes_results(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.modules.batch import flatten_batch

        entries = [make_result_entry(text="a"), make_result_entry(text="b")]
        batch = make_batch(state="JOB_STATE_SUCCEEDED", dest=make_dest(entries))
        result = flatten_batch(batch, changed=False)

        assert len(result["results"]) == 2
        assert result["results"][0]["text"] == "a"

    def test_terminal_state_without_dest_has_no_results_key(self, mock_genai):
        from ansible_collections.aknochow.gemini.plugins.modules.batch import flatten_batch

        batch = make_batch(state="JOB_STATE_FAILED", dest=None)
        result = flatten_batch(batch, changed=False)

        assert "results" not in result


class TestMainSubmit:
    def test_creates_batch_with_model_and_requests(self, mock_genai, monkeypatch):
        from ansible_collections.aknochow.gemini.plugins.modules import batch as batch_module

        requests = [{"contents": "hi"}]
        fake_module = make_fake_module({"model": "gemini-3.6-flash", "requests": requests})
        monkeypatch.setattr(batch_module, "AnsibleModule", lambda **kwargs: fake_module)
        mock_genai.Client.return_value.batches.create.return_value = make_batch(
            name="batches/new123", state="JOB_STATE_QUEUED"
        )

        batch_module.main()

        create_kwargs = mock_genai.Client.return_value.batches.create.call_args.kwargs
        assert create_kwargs["model"] == "gemini-3.6-flash"
        assert create_kwargs["src"] == requests
        assert create_kwargs["config"] is None

        result = fake_module.exit_json.call_args.kwargs
        assert result["changed"] is True
        assert result["name"] == "batches/new123"

    def test_display_name_builds_config(self, mock_genai, monkeypatch):
        from ansible_collections.aknochow.gemini.plugins.modules import batch as batch_module

        fake_module = make_fake_module(
            {"model": "gemini-3.6-flash", "requests": [{"contents": "hi"}], "display_name": "nightly-run"}
        )
        monkeypatch.setattr(batch_module, "AnsibleModule", lambda **kwargs: fake_module)
        mock_genai.Client.return_value.batches.create.return_value = make_batch()

        batch_module.main()

        config_kwargs = mock_genai.types.CreateBatchJobConfig.call_args.kwargs
        assert config_kwargs["display_name"] == "nightly-run"

    def test_fails_without_model_or_requests(self, mock_genai, monkeypatch):
        from ansible_collections.aknochow.gemini.plugins.modules import batch as batch_module

        fake_module = make_fake_module({}, fails=True)
        monkeypatch.setattr(batch_module, "AnsibleModule", lambda **kwargs: fake_module)

        with pytest.raises(SystemExit):
            batch_module.main()

        fake_module.fail_json.assert_called_once()


class TestMainPoll:
    def test_polling_existing_batch_reports_changed_false(self, mock_genai, monkeypatch):
        from ansible_collections.aknochow.gemini.plugins.modules import batch as batch_module

        fake_module = make_fake_module({"name": "batches/abc123"})
        monkeypatch.setattr(batch_module, "AnsibleModule", lambda **kwargs: fake_module)
        mock_genai.Client.return_value.batches.get.return_value = make_batch(state="JOB_STATE_RUNNING")

        batch_module.main()

        mock_genai.Client.return_value.batches.get.assert_called_once_with(name="batches/abc123")
        assert fake_module.exit_json.call_args.kwargs["changed"] is False


class TestMainCancel:
    def test_cancel_calls_cancel_then_refetches(self, mock_genai, monkeypatch):
        from ansible_collections.aknochow.gemini.plugins.modules import batch as batch_module

        fake_module = make_fake_module({"name": "batches/abc123", "state": "absent"})
        monkeypatch.setattr(batch_module, "AnsibleModule", lambda **kwargs: fake_module)
        mock_genai.Client.return_value.batches.get.return_value = make_batch(state="JOB_STATE_CANCELLED")

        batch_module.main()

        mock_genai.Client.return_value.batches.cancel.assert_called_once_with(name="batches/abc123")
        mock_genai.Client.return_value.batches.get.assert_called_once_with(name="batches/abc123")
        result = fake_module.exit_json.call_args.kwargs
        assert result["changed"] is True
        assert result["state"] == "JOB_STATE_CANCELLED"

    def test_cancel_without_name_fails(self, mock_genai, monkeypatch):
        from ansible_collections.aknochow.gemini.plugins.modules import batch as batch_module

        fake_module = make_fake_module({"state": "absent"}, fails=True)
        monkeypatch.setattr(batch_module, "AnsibleModule", lambda **kwargs: fake_module)

        with pytest.raises(SystemExit):
            batch_module.main()

        fake_module.fail_json.assert_called_once()


class TestMainWait:
    def test_polls_until_terminal_state(self, mock_genai, monkeypatch):
        from ansible_collections.aknochow.gemini.plugins.modules import batch as batch_module

        fake_module = make_fake_module({"name": "batches/abc123", "wait": True, "wait_timeout": 600})
        monkeypatch.setattr(batch_module, "AnsibleModule", lambda **kwargs: fake_module)

        running_batch = make_batch(state="JOB_STATE_RUNNING")
        succeeded_batch = make_batch(
            state="JOB_STATE_SUCCEEDED", dest=make_dest([make_result_entry(text="done")])
        )
        mock_genai.Client.return_value.batches.get.side_effect = [running_batch, succeeded_batch]
        monkeypatch.setattr(batch_module.time, "sleep", lambda seconds: None)
        monkeypatch.setattr(batch_module.time, "monotonic", lambda: 0.0)

        batch_module.main()

        result = fake_module.exit_json.call_args.kwargs
        assert result["state"] == "JOB_STATE_SUCCEEDED"
        assert result["results"][0]["text"] == "done"

    def test_timeout_fails_with_clear_message(self, mock_genai, monkeypatch):
        from ansible_collections.aknochow.gemini.plugins.modules import batch as batch_module

        fake_module = make_fake_module(
            {"name": "batches/abc123", "wait": True, "wait_timeout": 10}, fails=True
        )
        monkeypatch.setattr(batch_module, "AnsibleModule", lambda **kwargs: fake_module)
        mock_genai.Client.return_value.batches.get.return_value = make_batch(state="JOB_STATE_RUNNING")
        monkeypatch.setattr(batch_module.time, "sleep", lambda seconds: None)
        # First call establishes the deadline (time.monotonic() + timeout),
        # second is the while-loop's own timeout check reporting elapsed
        # time past that deadline.
        monkeypatch.setattr(batch_module.time, "monotonic", MagicMock(side_effect=[0.0, 100.0]))

        with pytest.raises(SystemExit):
            batch_module.main()

        fake_module.fail_json.assert_called_once()
        assert "Timed out" in fake_module.fail_json.call_args.kwargs["msg"]
