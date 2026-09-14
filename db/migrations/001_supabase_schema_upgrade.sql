-- =============================================================================
-- Aeropt: Supabase Schema Upgrade 001  (ADDITIVE ONLY)
-- =============================================================================

-- 1. users
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS exam_date             date,
  ADD COLUMN IF NOT EXISTS daily_goal_minutes    smallint  DEFAULT 30,
  ADD COLUMN IF NOT EXISTS grade_level           text
    CHECK (grade_level = ANY (ARRAY['CLASS_11'::text, 'CLASS_12'::text, 'DROPPER'::text])),
  ADD COLUMN IF NOT EXISTS onboarding_completed  boolean   DEFAULT false;

-- 2. sessions — fix bare ARRAY type, add session metadata
ALTER TABLE public.sessions
  ALTER COLUMN concepts_touched TYPE text[]
    USING COALESCE(concepts_touched::text[], '{}');

ALTER TABLE public.sessions
  ADD COLUMN IF NOT EXISTS session_type          text
    CHECK (session_type = ANY (ARRAY['DOUBT'::text,'PRACTICE'::text,'DIAGNOSTIC'::text,'REVISION'::text,'ASSESSMENT'::text])),
  ADD COLUMN IF NOT EXISTS duration_seconds      integer   DEFAULT 0,
  ADD COLUMN IF NOT EXISTS goal_minutes_at_start smallint  DEFAULT 0,
  ADD COLUMN IF NOT EXISTS last_decision         jsonb;

-- 3. chat_turns — observability + student feedback
ALTER TABLE public.chat_turns
  ADD COLUMN IF NOT EXISTS decision             jsonb,
  ADD COLUMN IF NOT EXISTS content_ids_served   text[]    DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS student_feedback     text
    CHECK (student_feedback = ANY (ARRAY['too_easy'::text,'too_hard'::text,'wrong_topic'::text]));

-- 4. user_concept_state — spaced repetition + repeat prevention
ALTER TABLE public.user_concept_state
  ADD COLUMN IF NOT EXISTS next_review_at   timestamp without time zone,
  ADD COLUMN IF NOT EXISTS is_decaying      boolean   DEFAULT false,
  ADD COLUMN IF NOT EXISTS last_content_ids text[]    DEFAULT '{}';

-- 5. daily_activity (NEW)
CREATE TABLE IF NOT EXISTS public.daily_activity (
  user_id              uuid      NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
  activity_date        date      NOT NULL DEFAULT CURRENT_DATE,
  minutes_studied      smallint  DEFAULT 0,
  questions_attempted  smallint  DEFAULT 0,
  correct_answers      smallint  DEFAULT 0,
  doubts_asked         smallint  DEFAULT 0,
  goal_met             boolean   DEFAULT false,
  streak_day           integer   DEFAULT 0,
  subjects_touched     text[]    DEFAULT '{}',
  CONSTRAINT daily_activity_pkey PRIMARY KEY (user_id, activity_date)
);

-- 6. session_skips (NEW)
CREATE TABLE IF NOT EXISTS public.session_skips (
  skip_id     uuid  NOT NULL DEFAULT gen_random_uuid(),
  user_id     uuid  NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
  concept_id  text  NOT NULL,
  skipped_at  timestamp without time zone DEFAULT now(),
  reason      text,
  expires_at  timestamp without time zone DEFAULT (now() + interval '3 days'),
  CONSTRAINT session_skips_pkey PRIMARY KEY (skip_id)
);

-- 7. Indexes
CREATE INDEX IF NOT EXISTS idx_ucs_user_proficiency   ON public.user_concept_state(user_id, proficiency_score ASC);
CREATE INDEX IF NOT EXISTS idx_ucs_flagged_weak        ON public.user_concept_state(user_id) WHERE flagged_weak = true;
CREATE INDEX IF NOT EXISTS idx_ucs_decaying            ON public.user_concept_state(user_id) WHERE is_decaying = true;
CREATE INDEX IF NOT EXISTS idx_chat_turns_session_order ON public.chat_turns(session_id, turn_index ASC);
CREATE INDEX IF NOT EXISTS idx_daily_activity_user_date ON public.daily_activity(user_id, activity_date DESC);
CREATE INDEX IF NOT EXISTS idx_skips_user_active        ON public.session_skips(user_id, concept_id) WHERE expires_at > now();
CREATE INDEX IF NOT EXISTS idx_attempts_user_concept    ON public.user_attempts(user_id, concept_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_user_started    ON public.sessions(user_id, started_at DESC);
