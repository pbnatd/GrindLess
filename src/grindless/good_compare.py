from __future__ import annotations

import argparse
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from .good_import import GoodArtifact, GoodDocument, import_good


CORE_FIELDS = (
    "setKey",
    "slotKey",
    "rarity",
    "level",
    "mainStatKey",
    "substats",
    "location",
    "lock",
)


def load_good_document(path: str | Path) -> tuple[dict[str, Any], GoodDocument]:
    file_path = Path(path)
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid GOOD JSON in {file_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"GOOD root in {file_path} must be an object")

    # The public importer performs both schema validation and domain-key mapping.
    import_good(payload)
    return payload, GoodDocument.model_validate(payload)


def compare_good_files(reference: str | Path, candidate: str | Path) -> dict[str, Any]:
    reference_payload, reference_document = load_good_document(reference)
    candidate_payload, candidate_document = load_good_document(candidate)
    result = compare_good_documents(reference_document, candidate_document)
    result["files"] = {
        "reference": str(Path(reference).expanduser().resolve()),
        "candidate": str(Path(candidate).expanduser().resolve()),
    }
    result["representation_differences"] = _representation_differences(
        reference_payload, candidate_payload
    )
    return result


def compare_good_documents(
    reference: GoodDocument,
    candidate: GoodDocument,
) -> dict[str, Any]:
    reference_signatures = Counter(_artifact_signature(item) for item in reference.artifacts)
    candidate_signatures = Counter(_artifact_signature(item) for item in candidate.artifacts)
    exact_matches = sum((reference_signatures & candidate_signatures).values())
    reference_count = len(reference.artifacts)
    candidate_count = len(candidate.artifacts)

    positional = _positional_comparison(reference.artifacts, candidate.artifacts)
    equivalent = (
        reference_count == candidate_count
        and exact_matches == reference_count
    )
    return {
        "equivalent": equivalent,
        "reference_artifacts": reference_count,
        "candidate_artifacts": candidate_count,
        "exact_core_matches": exact_matches,
        "core_accuracy_percent": round(
            100.0 * exact_matches / reference_count if reference_count else 100.0,
            3,
        ),
        "missing_core_records": sum((reference_signatures - candidate_signatures).values()),
        "extra_core_records": sum((candidate_signatures - reference_signatures).values()),
        "metadata": {
            "reference": {"source": reference.source, "version": reference.version},
            "candidate": {"source": candidate.source, "version": candidate.version},
        },
        "positional_comparison": positional,
        "comparison_contract": {
            "artifact_order": "ignored for exact_core_matches",
            "substat_order": "ignored",
            "numeric_representation": "normalized",
            "missing_location": "equivalent to empty location",
            "missing_lock": "equivalent to false",
        },
    }


def _artifact_signature(artifact: GoodArtifact) -> tuple[object, ...]:
    return (
        artifact.setKey,
        artifact.slotKey,
        artifact.rarity,
        artifact.level,
        artifact.mainStatKey,
        _substat_signature(artifact),
        artifact.location,
        artifact.lock,
    )


def _substat_signature(artifact: GoodArtifact) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (substat.key, _normalized_number(substat.value))
            for substat in artifact.substats
            if substat.key
        )
    )


def _normalized_number(value: float) -> str:
    return str(Decimal(str(value)).normalize())


def _positional_comparison(
    reference: list[GoodArtifact],
    candidate: list[GoodArtifact],
) -> dict[str, Any]:
    compared = min(len(reference), len(candidate))
    field_matches = Counter({field: 0 for field in CORE_FIELDS})
    exact = 0
    for expected, actual in zip(reference, candidate):
        if _artifact_signature(expected) == _artifact_signature(actual):
            exact += 1
        for field in CORE_FIELDS:
            expected_value = _field_value(expected, field)
            actual_value = _field_value(actual, field)
            if expected_value == actual_value:
                field_matches[field] += 1

    accuracy = {
        field: round(100.0 * field_matches[field] / compared if compared else 100.0, 3)
        for field in CORE_FIELDS
    }
    return {
        "applicable": len(reference) == len(candidate),
        "compared_positions": compared,
        "exact_positions": exact,
        "field_matches": dict(field_matches),
        "field_accuracy_percent": accuracy,
    }


def _field_value(artifact: GoodArtifact, field: str) -> object:
    if field == "substats":
        return _substat_signature(artifact)
    return getattr(artifact, field)


def _representation_differences(
    reference: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, int]:
    reference_artifacts = reference.get("artifacts", [])
    candidate_artifacts = candidate.get("artifacts", [])
    pairs = zip(reference_artifacts, candidate_artifacts)
    return {
        "candidate_added_empty_location": sum(
            "location" not in expected and actual.get("location") == ""
            for expected, actual in pairs
            if isinstance(expected, dict) and isinstance(actual, dict)
        )
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare two validated GOOD exports by artifact content"
    )
    parser.add_argument("reference", help="Known-good GOOD JSON")
    parser.add_argument("candidate", help="Newly extracted GOOD JSON")
    args = parser.parse_args()

    result = compare_good_files(args.reference, args.candidate)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["equivalent"] else 1)


if __name__ == "__main__":
    main()
