from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from grindless.good_compare import compare_good_files


EXAMPLE = Path(__file__).parents[1] / "examples" / "xiangling.good.json"


class GoodCompareTests(unittest.TestCase):
    def _write_pair(
        self, reference: dict[str, object], candidate: dict[str, object]
    ) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        reference_path = root / "reference.json"
        candidate_path = root / "candidate.json"
        reference_path.write_text(json.dumps(reference), encoding="utf-8")
        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
        return directory, reference_path, candidate_path

    def test_empty_location_and_artifact_order_are_semantically_equivalent(self) -> None:
        reference = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        candidate = copy.deepcopy(reference)
        candidate["artifacts"].reverse()
        for artifact in candidate["artifacts"]:
            artifact.setdefault("location", "")

        directory, reference_path, candidate_path = self._write_pair(reference, candidate)
        self.addCleanup(directory.cleanup)
        result = compare_good_files(reference_path, candidate_path)

        self.assertTrue(result["equivalent"])
        self.assertEqual(result["exact_core_matches"], 6)
        self.assertLess(result["positional_comparison"]["exact_positions"], 6)

    def test_substat_order_and_numeric_spelling_are_equivalent(self) -> None:
        reference = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        candidate = copy.deepcopy(reference)
        candidate["artifacts"][0]["substats"].reverse()
        candidate["artifacts"][0]["substats"][0]["value"] = float(
            candidate["artifacts"][0]["substats"][0]["value"]
        )

        directory, reference_path, candidate_path = self._write_pair(reference, candidate)
        self.addCleanup(directory.cleanup)
        result = compare_good_files(reference_path, candidate_path)

        self.assertTrue(result["equivalent"])

    def test_changed_substat_is_reported_as_a_core_mismatch(self) -> None:
        reference = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        candidate = copy.deepcopy(reference)
        candidate["artifacts"][0]["substats"][0]["value"] += 1

        directory, reference_path, candidate_path = self._write_pair(reference, candidate)
        self.addCleanup(directory.cleanup)
        result = compare_good_files(reference_path, candidate_path)

        self.assertFalse(result["equivalent"])
        self.assertEqual(result["exact_core_matches"], 5)
        self.assertEqual(
            result["positional_comparison"]["field_matches"]["substats"], 5
        )


if __name__ == "__main__":
    unittest.main()
