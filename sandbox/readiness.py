"""JEE readiness score — computed from existing proficiency signals (read-only)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from users.supabase_sync import get_supabase_client, is_supabase_configured


def compute_readiness(user) -> Dict[str, Any]:
    profile = getattr(user, "student_profile", None)
    target_label = getattr(profile, "target_exam", "JEE") if profile else "JEE"

    overall = 50
    concept_mastery = 50
    prerequisite_health = 50
    pyq_performance = 50
    consistency = 50
    concepts_tracked = 0

    if is_supabase_configured() and user.supabase_user_id:
        client = get_supabase_client()
        if client is not None:
            res = (
                client.table("user_concept_state")
                .select("proficiency_score, flagged_weak, is_cold_start")
                .eq("user_id", str(user.supabase_user_id))
                .execute()
            )
            rows = res.data or []
            concepts_tracked = len(rows)
            if rows:
                scores = [float(r.get("proficiency_score", 0.5)) for r in rows]
                concept_mastery = round(sum(scores) / len(scores) * 100)
                weak_count = sum(1 for r in rows if r.get("flagged_weak"))
                cold_count = sum(1 for r in rows if r.get("is_cold_start"))
                prerequisite_health = max(0, 100 - round((weak_count / len(rows)) * 100))
                if cold_count:
                    prerequisite_health = max(0, prerequisite_health - min(20, cold_count * 2))

    try:
        from roadmap.generator import get_active_learning_path

        path = get_active_learning_path(user)
        if path and path.total_nodes:
            completed = path.nodes.filter(status__in=["completed", "skipped"]).count()
            pyq_performance = round((completed / path.total_nodes) * 100)
    except Exception:
        pass

    try:
        from analytics.models import Streak

        streak = Streak.objects.filter(user=user).order_by("-updated_at").first()
        if streak and streak.current_streak:
            consistency = min(100, streak.current_streak * 12)
    except Exception:
        pass

    overall = round(
        concept_mastery * 0.40
        + prerequisite_health * 0.20
        + pyq_performance * 0.25
        + consistency * 0.05
        + 50 * 0.10  # mock placeholder until Assessment loop ships
    )

    state = "Explorer"
    if overall >= 85:
        state = "Exam-Ready"
    elif overall >= 60:
        state = "Challenger"
    elif overall >= 20:
        state = "Builder"

    return {
        "overall": overall,
        "target_exam": target_label,
        "components": {
            "concept_mastery": concept_mastery,
            "prerequisite_health": prerequisite_health,
            "pyq_performance": pyq_performance,
            "mock_performance": 50,
            "consistency": consistency,
        },
        "concepts_tracked": concepts_tracked,
        "graduation_state": state,
    }
