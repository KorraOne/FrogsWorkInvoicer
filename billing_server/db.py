import os
import sqlite3
from contextlib import contextmanager

from config import DATABASE_URL


def _ensure_database_dir():
    db_dir = os.path.dirname(os.path.abspath(DATABASE_URL))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


def _connect():
    _ensure_database_dir()
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_db_writable():
    """Return None if the database can accept writes, else an error message."""
    try:
        with get_db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("ROLLBACK")
        return None
    except sqlite3.OperationalError as exc:
        return str(exc)
    except OSError as exc:
        return str(exc)


def _schema_ready(conn):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'accounts'"
    ).fetchone()
    return row is not None


def init_db():
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                cap_enabled INTEGER NOT NULL DEFAULT 0,
                cap_amount_ex_gst TEXT,
                billing_cycle TEXT NOT NULL DEFAULT 'quarterly',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );

            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                invoice_number INTEGER NOT NULL,
                amount_ex_gst TEXT NOT NULL,
                usage_month TEXT NOT NULL,
                cap_overridden INTEGER NOT NULL DEFAULT 0,
                committed_at TEXT NOT NULL,
                UNIQUE(account_id, invoice_number),
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );

            CREATE TABLE IF NOT EXISTS monthly_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                usage_month TEXT NOT NULL,
                total_ex_gst TEXT NOT NULL,
                fee_accrued TEXT NOT NULL,
                UNIQUE(account_id, usage_month),
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );

            CREATE TABLE IF NOT EXISTS platform_invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                billing_cycle_start TEXT NOT NULL,
                billing_cycle_end TEXT NOT NULL,
                line_items_json TEXT NOT NULL,
                subtotal_ex_gst TEXT NOT NULL,
                gst_amount TEXT NOT NULL,
                amount_due TEXT NOT NULL,
                pdf_filename TEXT,
                invoice_number TEXT,
                created_at TEXT NOT NULL,
                paid_at TEXT,
                emailed_at TEXT,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );
            """
        )
        cols = {row[1] for row in conn.execute("PRAGMA table_info(platform_invoices)").fetchall()}
        if "invoice_number" not in cols:
            conn.execute("ALTER TABLE platform_invoices ADD COLUMN invoice_number TEXT")
        if "emailed_at" not in cols:
            conn.execute("ALTER TABLE platform_invoices ADD COLUMN emailed_at TEXT")
        if not _schema_ready(conn):
            raise RuntimeError(
                f"Billing database schema missing after init (DATABASE_URL={DATABASE_URL!r}). "
                "Stop the server, delete the database file, and restart."
            )
