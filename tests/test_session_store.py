from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from grindless.session_store import SQLiteSessionStore


class SessionStoreTests(unittest.TestCase):
    def test_round_trip_without_raw_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteSessionStore(Path(directory) / "state.sqlite3")
            payload = {
                "policy": "economy",
                "target_slots": ["sands"],
                "resin_budget": 200,
                "seed": 386,
                "result": {
                    "decision": "stop",
                    "reason": "all_slot_goals_met",
                    "runs": 5,
                    "resin_spent": 100,
                    "resin_remaining": 100,
                },
                "narration": {
                    "backend": "offline",
                    "model": None,
                    "status": "offline",
                },
            }

            summary = store.save(payload)
            stored = store.get(summary.session_id)

            self.assertEqual(store.list()[0].session_id, summary.session_id)
            self.assertEqual(stored.payload["seed"], 386)
            self.assertNotIn("inventory", stored.payload)


if __name__ == "__main__":
    unittest.main()
