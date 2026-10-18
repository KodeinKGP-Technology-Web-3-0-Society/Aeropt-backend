"""Broad Physics syllabus units for the 3-step onboarding self-assessment."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple

UNIT_ORDER = [
    "Mechanics",
    "Thermodynamics",
    "Waves & Sound",
    "Optics",
    "Electrostatics & Current",
    "Magnetism",
    "Modern Physics",
]

# Canonical JEE Physics chapter → unit. Unknown live chapters fall through to yaml unit or Other.
CHAPTER_TO_UNIT: Dict[str, str] = {
    # Physics
    "Laws of Motion": "Mechanics",
    "Work Energy & Power": "Mechanics",
    "Rotational Motion": "Mechanics",
    "Kinematics": "Mechanics",
    "Units and Dimensions": "Mechanics",
    "Vectors": "Mechanics",
    "Centre of Mass": "Mechanics",
    "Gravitation": "Mechanics",
    "Fluid Mechanics": "Mechanics",
    "Properties of Matter": "Mechanics",
    "Simple Harmonic Motion": "Mechanics",
    "Thermal Properties": "Thermodynamics",
    "Thermodynamics": "Thermodynamics",
    "Kinetic Theory": "Thermodynamics",
    "Waves": "Waves & Sound",
    "Sound": "Waves & Sound",
    "Wave Optics": "Optics",
    "Ray Optics": "Optics",
    "Optics": "Optics",
    "Electrostatics": "Electrostatics & Current",
    "Current Electricity": "Electrostatics & Current",
    "Capacitance": "Electrostatics & Current",
    "Magnetism": "Magnetism",
    "Magnetic Effects of Current": "Magnetism",
    "Electromagnetic Induction": "Magnetism",
    "Alternating Current": "Magnetism",
    "Electromagnetic Waves": "Magnetism",
    "Dual Nature of Radiation": "Modern Physics",
    "Atoms": "Modern Physics",
    "Nuclei": "Modern Physics",
    "Semiconductor": "Modern Physics",
    "Modern Physics": "Modern Physics",
    # Chemistry
    "Mole Concept & Stoichiometry": "Physical Chemistry",
    "Atomic Structure": "Physical Chemistry",
    "States of Matter": "Physical Chemistry",
    "Chemical Thermodynamics & Energetics": "Physical Chemistry",
    "Chemical & Ionic Equilibrium": "Physical Chemistry",
    "Redox Reactions & Electrochemistry": "Physical Chemistry",
    "Chemical Kinetics": "Physical Chemistry",
    "Solid State & Solutions": "Physical Chemistry",
    "Surface Chemistry & Metallurgy": "Physical Chemistry",
    "Periodic Table & Periodicity": "Inorganic Chemistry",
    "Chemical Bonding & Molecular Structure": "Inorganic Chemistry",
    "Coordination Compounds": "Inorganic Chemistry",
    "General Organic Chemistry & Hydrocarbons": "Organic Chemistry",
    "Haloalkanes, Alcohols & Ethers": "Organic Chemistry",
    "Aldehydes, Ketones & Carboxylic Acids": "Organic Chemistry",
    "Nitrogen Compounds & Biomolecules": "Organic Chemistry",
    # Mathematics
    "Quadratic Equations": "Algebra",
    "Sequences & Series": "Algebra",
    "Complex Numbers": "Algebra",
    "Permutations & Combinations": "Algebra",
    "Binomial Theorem": "Algebra",
    "Matrices & Determinants": "Algebra",
    "Trigonometric Ratios & Identities": "Trigonometry",
    "Straight Lines & Circles": "Coordinate Geometry",
    "Conic Sections": "Coordinate Geometry",
    "Functions, Limits & Continuity": "Calculus",
    "Differentiation & Applications": "Calculus",
    "Integration": "Calculus",
    "Vectors & 3D Geometry": "Vectors & 3D",
    "Probability & Statistics": "Probability & Statistics",
}

SUBJECT_UNITS: Dict[str, List[Dict[str, Any]]] = {
    "Physics": [
        {"name": "Mechanics", "chapters": ["Laws of Motion", "Work Energy & Power", "Rotational Motion", "Kinematics", "Units and Dimensions", "Vectors", "Centre of Mass", "Gravitation", "Fluid Mechanics", "Properties of Matter", "Simple Harmonic Motion"]},
        {"name": "Thermodynamics", "chapters": ["Thermal Properties", "Thermodynamics", "Kinetic Theory"]},
        {"name": "Waves & Sound", "chapters": ["Waves", "Sound"]},
        {"name": "Optics", "chapters": ["Wave Optics", "Ray Optics", "Optics"]},
        {"name": "Electrostatics & Current", "chapters": ["Electrostatics", "Current Electricity", "Capacitance"]},
        {"name": "Magnetism & EMI", "chapters": ["Magnetism", "Magnetic Effects of Current", "Electromagnetic Induction", "Alternating Current", "Electromagnetic Waves"]},
        {"name": "Modern Physics", "chapters": ["Dual Nature of Radiation", "Atoms", "Nuclei", "Semiconductor", "Modern Physics"]},
    ],
    "Chemistry": [
        {"name": "Physical Chemistry", "chapters": ["Mole Concept & Stoichiometry", "Atomic Structure", "States of Matter", "Chemical Thermodynamics & Energetics", "Chemical & Ionic Equilibrium", "Redox Reactions & Electrochemistry", "Chemical Kinetics", "Solid State & Solutions", "Surface Chemistry & Metallurgy"]},
        {"name": "Inorganic Chemistry", "chapters": ["Periodic Table & Periodicity", "Chemical Bonding & Molecular Structure", "Coordination Compounds"]},
        {"name": "Organic Chemistry", "chapters": ["General Organic Chemistry & Hydrocarbons", "Haloalkanes, Alcohols & Ethers", "Aldehydes, Ketones & Carboxylic Acids", "Nitrogen Compounds & Biomolecules"]},
    ],
    "Mathematics": [
        {"name": "Algebra", "chapters": ["Quadratic Equations", "Sequences & Series", "Complex Numbers", "Permutations & Combinations", "Binomial Theorem", "Matrices & Determinants"]},
        {"name": "Trigonometry", "chapters": ["Trigonometric Ratios & Identities"]},
        {"name": "Coordinate Geometry", "chapters": ["Straight Lines & Circles", "Conic Sections"]},
        {"name": "Calculus", "chapters": ["Functions, Limits & Continuity", "Differentiation & Applications", "Integration"]},
        {"name": "Vectors & 3D", "chapters": ["Vectors & 3D Geometry"]},
        {"name": "Probability & Statistics", "chapters": ["Probability & Statistics"]},
    ],
}


def _yaml_chapter_units() -> Dict[str, str]:
    from roadmap.syllabus import load_physics_syllabus

    mapping: Dict[str, str] = {}
    spec = load_physics_syllabus()
    for chapter in spec.get("chapters", []) or []:
        name = chapter.get("name")
        unit = chapter.get("unit")
        if name and unit:
            mapping[name] = unit
    return mapping


def unit_for_chapter(chapter: str) -> str:
    yaml_units = _yaml_chapter_units()
    if chapter in yaml_units:
        return yaml_units[chapter]
    if chapter in CHAPTER_TO_UNIT:
        return CHAPTER_TO_UNIT[chapter]
    return "Mechanics"


def chapters_for_unit(unit: str, available_chapters: Iterable[str] | None = None) -> List[str]:
    names = list(available_chapters) if available_chapters is not None else list(_all_known_chapters())
    return [name for name in names if unit_for_chapter(name) == unit]


def _all_known_chapters() -> List[str]:
    from roadmap.syllabus import chapter_order_map

    order = chapter_order_map()
    names = set(order.keys()) | set(CHAPTER_TO_UNIT.keys()) | set(_yaml_chapter_units().keys())
    return sorted(names, key=lambda ch: order.get(ch, 99))


def expand_unit_coverage(
    unit_coverage: Dict[str, str],
    available_chapters: Iterable[str] | None = None,
) -> Tuple[List[str], Dict[str, str]]:
    """Expand unit-level confidence into covered_chapters + self_assessed_coverage."""
    chapters: List[str] = []
    depth_map: Dict[str, str] = {}
    available = list(available_chapters) if available_chapters is not None else None
    for unit, depth in (unit_coverage or {}).items():
        if not depth or depth in ("not_started", "none"):
            continue
        for chapter in chapters_for_unit(unit, available):
            if chapter not in chapters:
                chapters.append(chapter)
            depth_map[chapter] = depth
    return chapters, depth_map


def group_chapters_into_units(chapters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_unit: Dict[str, List[str]] = defaultdict(list)
    for chapter in chapters:
        name = chapter.get("name") if isinstance(chapter, dict) else chapter
        if not name:
            continue
        by_unit[unit_for_chapter(name)].append(name)

    units: List[Dict[str, Any]] = []
    seen = set()
    for unit_name in UNIT_ORDER:
        seen.add(unit_name)
        chs = by_unit.get(unit_name) or []
        if not chs:
            continue
        units.append({"name": unit_name, "chapters": chs})
    for unit_name, chs in by_unit.items():
        if unit_name in seen:
            continue
        units.append({"name": unit_name, "chapters": chs})
    return units
