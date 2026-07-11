"""Load canonical JEE Physics syllabus spec."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml

SYLLABUS_PATH = Path(__file__).resolve().parent / "data" / "physics_syllabus.yaml"


@lru_cache(maxsize=1)
def load_physics_syllabus() -> Dict[str, Any]:
    with SYLLABUS_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def syllabus_concept_map() -> Dict[str, Dict[str, Any]]:
    """concept_id -> merged spec fields."""
    spec = load_physics_syllabus()
    result: Dict[str, Dict[str, Any]] = {}
    for chapter in spec.get("chapters", []):
        chapter_name = chapter.get("name", "")
        chapter_order = chapter.get("order", 99)
        for concept in chapter.get("concepts", []):
            concept_id = concept.get("id")
            if not concept_id:
                continue
            result[concept_id] = {
                **concept,
                "chapter": chapter_name,
                "chapter_order": chapter_order,
            }
    return result


def chapter_order_map() -> Dict[str, int]:
    spec = load_physics_syllabus()
    return {
        chapter.get("name", ""): chapter.get("order", 99)
        for chapter in spec.get("chapters", [])
    }


def prerequisite_map() -> Dict[str, List[str]]:
    return {
        concept_id: list(spec.get("prerequisites") or [])
        for concept_id, spec in syllabus_concept_map().items()
    }
