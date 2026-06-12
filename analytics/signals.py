"""
analytics/signals.py
====================
Django signals that update analytics data when the chatbot app processes a message.

PLANNED SIGNALS
---------------

Signal: concept_mentioned
  - Defined here and fired by chatbot/views.py after every assistant LLM response
  - Carries: user, list of { concept_name, chapter, score_at_time, is_correct }

Handler: on_concept_mentioned(sender, user, concepts_data, **kwargs)
  - For each concept in concepts_data:
      1. Upsert ConceptProficiency (update score, increment attempts, recalculate trend)
      2. Upsert DailyProficiencySnapshot for today's date
  - Update StudyStreak (set last_study_date = today, increment current_streak if needed)
  - Invalidate Redis cache keys: dashboard:{user.id}, progress:{user.id}

Signal: practice_attempt_completed
  - Fired by analytics/views.py PracticeAttemptCreateView after saving an attempt
  - Carries: user, concept_name, chapter, is_correct, mistake_type

Handler: on_practice_attempt_completed(sender, user, concept_name, chapter, is_correct, mistake_type, **kwargs)
  - Upsert ConceptProficiency
  - Update StudyStreak
  - Upsert DailyProficiencySnapshot
  - Invalidate Redis cache
"""

# Signals will be implemented here.
