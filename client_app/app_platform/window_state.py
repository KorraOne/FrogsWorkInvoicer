"""Persist desktop window size and position."""

import json
import os

import storage

_STATE_FILE = "window_state.json"


def _state_path():
    return os.path.join(storage.get_bootstrap_dir(), _STATE_FILE)


def load_window_state():
    defaults = {
        "maximized": True,
        "width": None,
        "height": None,
        "x": None,
        "y": None,
    }
    path = _state_path()
    if not os.path.exists(path):
        return defaults
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {**defaults, **data}
    except (OSError, json.JSONDecodeError, TypeError):
        return defaults


def save_window_state(state):
    path = _state_path()
    payload = {
        "maximized": bool(state.get("maximized", False)),
        "width": state.get("width"),
        "height": state.get("height"),
        "x": state.get("x"),
        "y": state.get("y"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
