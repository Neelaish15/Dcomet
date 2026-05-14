import json
import os
import sqlite3
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List


class PersistenceStore:
    """Small SQLite-backed event and trade store for audit and replay."""

    def __init__(self, db_path: str = "logs/dcomet.db"):
        self.db_path = db_path
        self._lock = Lock()
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    correlation_id TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    seller_id TEXT,
                    buyer_id TEXT,
                    quantity_w REAL,
                    quantity_kwh REAL,
                    price_usd REAL,
                    status TEXT,
                    explainability_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency (
                    key TEXT PRIMARY KEY,
                    endpoint TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def log_event(self, event_type: str, payload: Dict[str, Any], correlation_id: str | None = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO events(timestamp, event_type, correlation_id, payload_json) VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), event_type, correlation_id, json.dumps(payload)),
            )
            conn.commit()

    def upsert_trade(self, trade: Dict[str, Any]) -> None:
        explainability = trade.get("explainability", {})
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trades(trade_id, timestamp, seller_id, buyer_id, quantity_w, quantity_kwh, price_usd, status, explainability_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_id) DO UPDATE SET
                    timestamp=excluded.timestamp,
                    seller_id=excluded.seller_id,
                    buyer_id=excluded.buyer_id,
                    quantity_w=excluded.quantity_w,
                    quantity_kwh=excluded.quantity_kwh,
                    price_usd=excluded.price_usd,
                    status=excluded.status,
                    explainability_json=excluded.explainability_json
                """,
                (
                    trade.get("trade_id"),
                    trade.get("timestamp", datetime.now().isoformat()),
                    trade.get("seller_id"),
                    trade.get("buyer_id"),
                    float(trade.get("quantity_w", 0.0)),
                    float(trade.get("quantity_kwh", 0.0)),
                    float(trade.get("price_usd", 0.0)),
                    trade.get("status", "unknown"),
                    json.dumps(explainability),
                ),
            )
            conn.commit()

    def recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT timestamp, event_type, correlation_id, payload_json FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "timestamp": row["timestamp"],
                "event_type": row["event_type"],
                "correlation_id": row["correlation_id"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def recent_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "trade_id": row["trade_id"],
                "timestamp": row["timestamp"],
                "seller_id": row["seller_id"],
                "buyer_id": row["buyer_id"],
                "quantity_w": row["quantity_w"],
                "quantity_kwh": row["quantity_kwh"],
                "price_usd": row["price_usd"],
                "status": row["status"],
                "explainability": json.loads(row["explainability_json"] or "{}"),
            }
            for row in rows
        ]

    def get_idempotent_response(self, key: str, endpoint: str) -> Dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT response_json FROM idempotency WHERE key = ? AND endpoint = ?",
                (key, endpoint),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["response_json"])

    def save_idempotent_response(self, key: str, endpoint: str, response: Dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO idempotency(key, endpoint, response_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (key, endpoint, json.dumps(response), datetime.now().isoformat()),
            )
            conn.commit()
