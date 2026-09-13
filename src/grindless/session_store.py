from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class SessionSummary(BaseModel):
    session_id: str
    created_at: str
    backend: str
    model: str | None
    policy: str
    target_slots: list[str]
    resin_budget: int
    seed: int
    decision: str
    reason: str
    runs: int
    resin_spent: int
    resin_remaining: int
    narration_status: str


class StoredSession(BaseModel):
    summary: SessionSummary
    payload: dict[str, object]


class SQLiteSessionStore:
    """Local session history without the user's raw GOOD inventory."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._initialize()

    def save(self, payload: dict[str, object]) -> SessionSummary:
        session_id = uuid.uuid4().hex
        created_at = datetime.now(UTC).isoformat()
        narration = _mapping(payload["narration"])
        result = _mapping(payload["result"])
        summary = SessionSummary.model_validate(
            {
                "session_id": session_id,
                "created_at": created_at,
                "backend": narration["backend"],
                "model": narration.get("model"),
                "policy": payload["policy"],
                "target_slots": payload["target_slots"],
                "resin_budget": payload["resin_budget"],
                "seed": payload["seed"],
                "decision": result["decision"],
                "reason": result["reason"],
                "runs": result["runs"],
                "resin_spent": result["resin_spent"],
                "resin_remaining": result["resin_remaining"],
                "narration_status": narration["status"],
            }
        )
        stored_payload = dict(payload)
        stored_payload["session_id"] = session_id
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO farm_sessions (
                    id, created_at, backend, model, policy, target_slots_json,
                    resin_budget, seed, decision, reason, runs, resin_spent,
                    resin_remaining, narration_status, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    created_at,
                    summary.backend,
                    summary.model,
                    summary.policy,
                    json.dumps(summary.target_slots),
                    summary.resin_budget,
                    summary.seed,
                    summary.decision,
                    summary.reason,
                    summary.runs,
                    summary.resin_spent,
                    summary.resin_remaining,
                    summary.narration_status,
                    json.dumps(stored_payload, ensure_ascii=False),
                ),
            )
        return summary

    def list(self, limit: int = 20) -> list[SessionSummary]:
        if limit < 1 or limit > 100:
            raise ValueError("session history limit must be between 1 and 100")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, backend, model, policy, target_slots_json,
                       resin_budget, seed, decision, reason, runs, resin_spent,
                       resin_remaining, narration_status
                FROM farm_sessions ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_summary_from_row(row) for row in rows]

    def get(self, session_id: str) -> StoredSession:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, created_at, backend, model, policy, target_slots_json,
                       resin_budget, seed, decision, reason, runs, resin_spent,
                       resin_remaining, narration_status, payload_json
                FROM farm_sessions WHERE id=?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown farm session: {session_id}")
        return StoredSession(
            summary=_summary_from_row(row[:14]), payload=json.loads(row[14])
        )

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS farm_sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    backend TEXT NOT NULL,
                    model TEXT,
                    policy TEXT NOT NULL,
                    target_slots_json TEXT NOT NULL,
                    resin_budget INTEGER NOT NULL,
                    seed INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    runs INTEGER NOT NULL,
                    resin_spent INTEGER NOT NULL,
                    resin_remaining INTEGER NOT NULL,
                    narration_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_farm_sessions_created ON farm_sessions(created_at DESC)"
            )
        try:
            self.database_path.chmod(0o600)
        except OSError:
            pass

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("stored session section must be an object")
    return value


def _summary_from_row(row: tuple[Any, ...]) -> SessionSummary:
    return SessionSummary(
        session_id=str(row[0]),
        created_at=str(row[1]),
        backend=str(row[2]),
        model=str(row[3]) if row[3] is not None else None,
        policy=str(row[4]),
        target_slots=json.loads(str(row[5])),
        resin_budget=int(row[6]),
        seed=int(row[7]),
        decision=str(row[8]),
        reason=str(row[9]),
        runs=int(row[10]),
        resin_spent=int(row[11]),
        resin_remaining=int(row[12]),
        narration_status=str(row[13]),
    )
