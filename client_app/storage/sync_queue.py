"""FIFO offline mutation queue for cloud storage mode."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from storage.bootstrap import get_appdata_path

MUTATION_TYPES = frozenset(
    {
        "upsert_business",
        "upsert_customer",
        "delete_customer",
        "create_invoice",
        "update_invoice_status",
        "enqueue_email_send",
    }
)


def _queue_path() -> str:
    return os.path.join(get_appdata_path(), "sync_queue.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_queue() -> list[dict[str, Any]]:
    path = _queue_path()
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def save_queue(items: list[dict[str, Any]]) -> None:
    path = _queue_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


def enqueue(mutation_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if mutation_type not in MUTATION_TYPES:
        raise ValueError(f"Unknown mutation type: {mutation_type}")
    item = {
        "id": str(uuid.uuid4()),
        "type": mutation_type,
        "payload": payload,
        "created_at": _now_iso(),
        "attempts": 0,
    }
    items = load_queue()
    items.append(item)
    save_queue(items)
    return item


def has_pending() -> bool:
    return bool(load_queue())


def pending_count() -> int:
    return len(load_queue())


def peek_all() -> list[dict[str, Any]]:
    return list(load_queue())


def clear() -> None:
    save_queue([])


def remove_ids(ids: set[str]) -> None:
    if not ids:
        return
    items = [item for item in load_queue() if item.get("id") not in ids]
    save_queue(items)


def mark_attempt(item_id: str) -> None:
    items = load_queue()
    for item in items:
        if item.get("id") == item_id:
            item["attempts"] = int(item.get("attempts", 0)) + 1
            item["last_attempt_at"] = _now_iso()
            break
    save_queue(items)
