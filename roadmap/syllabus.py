"""Load canonical JEE syllabus specs — one YAML file per subject."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml

_DATA_DIR = Path(__file__).resolve().parent / "data"

# Subject name (as used in LearningPath.subject / the dashboard's subject
# cards) -> syllabus YAML filename. Add a new subject by dropping a file
# here and registering it — everything else (roadmap generation, ordering,
# prerequisite resolution) is already subject-agnostic.
_SYLLABUS_FILES: Dict[str, str] = {
    "Physics": "physics_syllabus.yaml",
    "Chemistry": "chemistry_syllabus.yaml",
    "Maths": "maths_syllabus.yaml",
}


@lru_cache(maxsize=None)
def load_syllabus(subject: str = "Physics") -> Dict[str, Any]:
    filename = _SYLLABUS_FILES.get(subject)
    if not filename:
        return {"subject": subject, "chapters": []}
    path = _DATA_DIR / filename
    if not path.exists():
        return {"subject": subject, "chapters": []}
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {"subject": subject, "chapters": []}


def load_physics_syllabus() -> Dict[str, Any]:
    """Kept for any external caller still importing this name directly."""
    return load_syllabus("Physics")


def syllabus_concept_map(subject: str = "Physics") -> Dict[str, Dict[str, Any]]:
    """concept_id -> merged spec fields, for one subject."""
    spec = load_syllabus(subject)
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
                "subject": subject,
            }
    return result


def chapter_order_map(subject: str = "Physics") -> Dict[str, int]:
    spec = load_syllabus(subject)
    return {
        chapter.get("name", ""): chapter.get("order", 99)
        for chapter in spec.get("chapters", [])
    }


def prerequisite_map(subject: str = "Physics") -> Dict[str, List[str]]:
    return {
        concept_id: list(spec.get("prerequisites") or [])
        for concept_id, spec in syllabus_concept_map(subject).items()
    }


def available_subjects() -> List[str]:
    """Subjects with an actual syllabus file on disk (vs. just registered)."""
    return [
        subject
        for subject, filename in _SYLLABUS_FILES.items()
        if (_DATA_DIR / filename).exists()
    ]
