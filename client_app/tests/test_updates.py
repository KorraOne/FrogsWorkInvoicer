"""Tests for app_platform.updates."""

import json

import app_platform.updates as updates


def test_version_less():
    assert updates.version_less("2.1.0", "2.2.0")
    assert not updates.version_less("2.2.0", "2.2.0")
    assert not updates.version_less("2.3.0", "2.2.0")


def test_merge_apply_result_records_failure(tmp_path, monkeypatch):
    bootstrap = tmp_path / "FrogsWork"
    bootstrap.mkdir()
    monkeypatch.setattr(updates, "_bootstrap_dir", lambda: str(bootstrap))

    state_path = bootstrap / "update_state.json"
    state_path.write_text(json.dumps({"dismissed_version": "2.2.1"}), encoding="utf-8")
    result_path = bootstrap / "update_apply_result.json"
    result_path.write_text(
        json.dumps({"ok": False, "version": "2.2.1", "error": "robocopy exit 16"}),
        encoding="utf-8",
    )

    state = updates.load_state()
    assert state["last_apply_failed"] is True
    assert state["last_apply_error"] == "robocopy exit 16"
    assert state["last_apply_version"] == "2.2.1"
    assert not result_path.exists()


def test_get_apply_failure_when_still_behind(tmp_path, monkeypatch):
    bootstrap = tmp_path / "FrogsWork"
    bootstrap.mkdir()
    monkeypatch.setattr(updates, "_bootstrap_dir", lambda: str(bootstrap))
    monkeypatch.setattr(updates, "APP_VERSION", "2.1.0")

    state_path = bootstrap / "update_state.json"
    state_path.write_text(
        json.dumps(
            {
                "last_apply_failed": True,
                "last_apply_version": "2.2.1",
                "last_apply_error": "robocopy exit 16",
            }
        ),
        encoding="utf-8",
    )

    failure = updates.get_apply_failure()
    assert failure is not None
    assert failure["version"] == "2.2.1"
    assert "robocopy" in failure["error"]


def test_mark_apply_started_clears_dismiss(tmp_path, monkeypatch):
    bootstrap = tmp_path / "FrogsWork"
    bootstrap.mkdir()
    monkeypatch.setattr(updates, "_bootstrap_dir", lambda: str(bootstrap))

    state_path = bootstrap / "update_state.json"
    state_path.write_text(json.dumps({"dismissed_version": "2.2.1"}), encoding="utf-8")

    updates.mark_apply_started("2.2.1")
    state = updates.load_state()
    assert "dismissed_version" not in state
    assert state["last_apply_version"] == "2.2.1"
    assert "last_apply_started_at" in state
