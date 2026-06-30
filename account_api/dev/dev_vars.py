"""Load account_api/dev/.dev.vars into os.environ (setdefault only)."""

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent


def load_dev_vars():
    path = APP_DIR / ".dev.vars"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
