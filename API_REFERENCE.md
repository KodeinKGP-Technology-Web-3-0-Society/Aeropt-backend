# Prepwise API Reference

Complete documentation for all REST endpoints in the Aeropt / Prepwise backend.

**Base URL:** `http://localhost:8000/api/v1/`

All routes are mounted under `/api/v1/` via `prepwise/urls.py` → `apis/urls.py`.

---

## Table of Contents

1. [General conventions](#general-conventions)
2. [Authentication](#authentication)
3. [Health check](#health-check)
4. [Users & accounts](#users--accounts)
5. [Content catalog](#content-catalog)
6. [Chat & study sessions](#chat--study-sessions)
7. [Analytics & learning progress](#analytics--learning-progress)
8. [Quick endpoint index](#quick-endpoint-index)

---

## General conventions

### Authentication

Most endpoints require a JWT access token:

```http
Authorization: Bearer <access_token>
```

Obtain tokens via `POST /api/v1/auth/token/` (see [Authentication](#authentication)).

When `CHATBOT_AUTH_DISABLED=true` in the environment, chat and analytics dev endpoints allow unauthenticated access and use a fallback dev user (`CHATBOT_DEV_EMAIL`).

### Pagination

List endpoints use page-based pagination (20 items per page by default):

| Query param | Description |
|-------------|-------------|
| `page` | Page number (1-based) |
| `page_size` | Items per page (max 100) |

**Response shape:**

```json
{
  "count": 100,
  "next": "http://localhost:8000/api/v1/users/?page=2",
  "previous": null,
  "results": [ ... ]
}
```

### Filtering, search, and ordering

Most `ModelViewSet` list endpoints support:

| Mechanism | Query param | Example |
|-----------|-------------|---------|
| Exact filter | field name | `?status=active` |
| Search (text) | `search` | `?search=torque` |
| Ordering | `ordering` | `?ordering=-created_at` |

Available filter/search/order fields are listed per resource below.

### Error response envelope

Errors are normalized by the custom exception handler:

```json
{
  "success": false,
  "data": null,
  "errors": [
    { "field": "email", "message": "This field is required." }
  ]
}
```

Successful ViewSet responses return the serializer payload directly (not wrapped). The envelope helpers in `apis/utils.py` are available for custom views if needed.

### Permissions overview

| Pattern | Behavior |
|---------|----------|
| **Catalog resources** (subjects, chapters, plans, etc.) | Authenticated users can list/create/update/delete. Staff users see all records. |
| **User-scoped resources** | Non-staff users only see and modify their own rows (`user` FK). Staff sees all. |
| **User primary-key resources** (`student-profiles`, `streaks`) | Keyed by `user_id`. Use your UUID or `me` (mapped to current user). |
| **Content flags** | Scoped to `reported_by` (the reporter). |
| **User CRUD** | List/create/destroy: admin only. Retrieve/update: self or admin. |

### Standard CRUD operations

Every `ModelViewSet` registered via DRF routers supports:

| Method | Path | Action |
|--------|------|--------|
| `GET` | `/resource/` | List (paginated) |
| `POST` | `/resource/` | Create |
| `GET` | `/resource/{id}/` | Retrieve |
| `PUT` | `/resource/{id}/` | Full update |
| `PATCH` | `/resource/{id}/` | Partial update |
| `DELETE` | `/resource/{id}/` | Delete |

`{id}` may be an integer, UUID, or `user_id` depending on the model.

---

## Authentication

### Obtain access & refresh tokens

```http
POST /api/v1/auth/token/
```

**Auth required:** No

**Body:**

```json
{
  "email": "student@example.com",
  "password": "yourpassword"
}
```

**Response:**

```json
{
  "access": "<access_token>",
  "refresh": "<refresh_token>"
}
```

Uses email as the login identifier (`AUTH_USER_MODEL = users.User`).

---

### Refresh access token

```http
POST /api/v1/auth/token/refresh/
```

**Auth required:** No

**Body:**

```json
{
  "refresh": "<refresh_token>"
}
```

**Response:**

```json
{
  "access": "<new_access_token>"
}
```

**Token lifetimes:** Access token — 60 minutes. Refresh token — 7 days (rotation enabled).

---

## Health check

### Service health

```http
GET /api/v1/health/
```

**Auth required:** No

**Response:**

```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

Used for uptime monitoring and load balancer health probes.

---

## Users & accounts

Base path: `/api/v1/users/`

### Users

```http
GET|POST   /api/v1/users/
GET|PUT|PATCH|DELETE /api/v1/users/{uuid}/
```

**Model:** `users.User` — core account (email login, role, status, profile fields).

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Read-only |
| `email` | string | Unique, login identifier |
| `phone` | string | Optional |
| `full_name` | string | |
| `role` | enum | `student`, `admin`, `content_collector`, `reviewer`, `mentor` |
| `status` | enum | `active`, `suspended`, `deleted` |
| `email_verified` | boolean | |
| `phone_verified` | boolean | |
| `avatar_url` | string | |
| `password` | string | Write-only on create/update |
| `last_login_at` | datetime | Read-only |
| `created_at`, `updated_at` | datetime | Read-only |

**Filters:** `role`, `status`, `email_verified`, `phone_verified`  
**Search:** `email`, `full_name`, `phone`  
**Ordering:** `created_at`, `email`, `full_name`

**Permissions:** Admin for list/create/delete. Retrieve/update: self or admin.

---

### OAuth accounts

```http
GET|POST   /api/v1/users/oauth-accounts/
GET|PUT|PATCH|DELETE /api/v1/users/oauth-accounts/{uuid}/
```

**Model:** `users.OAuthAccount` — linked Google/Apple OAuth identities.

| Field | Type | Notes |
|-------|------|-------|
| `user` | UUID | FK to User |
| `provider` | enum | `google`, `apple` |
| `provider_user_id` | string | Unique per provider |
| `email` | string | |

**Filters:** `provider`, `user`  
**Search:** `email`, `provider_user_id`  
**Scoped:** User sees only their own accounts (unless staff).

---

### Auth sessions

```http
GET|POST   /api/v1/users/auth-sessions/
GET|PUT|PATCH|DELETE /api/v1/users/auth-sessions/{uuid}/
```

**Model:** `users.AuthSession` — refresh token sessions for logout/revocation tracking.

| Field | Type | Notes |
|-------|------|-------|
| `user` | UUID | |
| `refresh_token_hash` | string | Write-only |
| `device_info` | JSON | |
| `ip_address` | string | |
| `expires_at` | datetime | |
| `revoked_at` | datetime | Null if active |

**Filters:** `user`, `revoked_at`  
**Scoped:** User sees only their own sessions.

---

### Student profiles

```http
GET|POST   /api/v1/users/student-profiles/
GET|PUT|PATCH|DELETE /api/v1/users/student-profiles/{user_id}/
```

**Model:** `users.StudentProfile` — exam target, onboarding, school info (OneToOne with User; PK = `user_id`).

| Field | Type | Notes |
|-------|------|-------|
| `user` | UUID | Primary key |
| `target_exam` | enum | `JEE_MAINS`, `JEE_ADVANCED`, `BOTH` |
| `target_year` | smallint | e.g. 2026 |
| `grade_level` | enum | `CLASS_11`, `CLASS_12`, `DROPPER` |
| `school_name`, `city`, `state` | string | |
| `daily_goal_minutes` | smallint | Default 30 |
| `onboarding_completed` | boolean | |
| `onboarding_step` | smallint | |

**Filters:** `target_exam`, `grade_level`, `onboarding_completed`  
**Search:** `school_name`, `city`, `state`  
**Lookup:** `user_id` — use `me` to access your own profile.

---

### User preferences

```http
GET|POST   /api/v1/users/preferences/
GET|PUT|PATCH|DELETE /api/v1/users/preferences/{user_id}/
```

**Model:** `users.UserPreferences` — notification and UI preferences (PK = `user_id`).

| Field | Type | Default |
|-------|------|---------|
| `notify_email` | boolean | true |
| `notify_push` | boolean | true |
| `notify_revision` | boolean | true |
| `theme` | string | `light` |
| `preferred_language` | string | `en` |

**Filters:** `theme`, `preferred_language`

---

### Plans

```http
GET|POST   /api/v1/users/plans/
GET|PUT|PATCH|DELETE /api/v1/users/plans/{id}/
```

**Model:** `users.Plan` — subscription plan catalog.

| Field | Type | Notes |
|-------|------|-------|
| `code` | string | Unique slug, e.g. `premium_monthly` |
| `name` | string | |
| `price_inr` | integer | Price in INR |
| `features` | JSON | Feature flags / metadata |
| `is_active` | boolean | |

**Filters:** `is_active`, `code`  
**Search:** `name`, `code`  
**Ordering:** `id`, `price_inr`, `name`

---

### Subscriptions

```http
GET|POST   /api/v1/users/subscriptions/
GET|PUT|PATCH|DELETE /api/v1/users/subscriptions/{uuid}/
```

**Model:** `users.Subscription` — user subscription to a plan.

| Field | Type | Notes |
|-------|------|-------|
| `user` | UUID | |
| `plan` / `plan_id` | object / int | Nested read, ID write |
| `status` | string | e.g. `active`, `canceled` |
| `provider` | string | Payment provider |
| `external_subscription_id` | string | |
| `started_at` | datetime | Required on create |
| `current_period_end` | datetime | |
| `canceled_at` | datetime | |

**Filters:** `status`, `provider`, `plan`, `user`  
**Scoped:** User sees only their subscriptions.

---

### Achievements

```http
GET|POST   /api/v1/users/achievements/
GET|PUT|PATCH|DELETE /api/v1/users/achievements/{id}/
```

**Model:** `users.Achievement` — global achievement definitions.

| Field | Type | Notes |
|-------|------|-------|
| `code` | string | Unique |
| `name` | string | |
| `description` | text | |
| `icon` | string | Icon identifier |

**Filters:** `code`  
**Search:** `name`, `code`, `description`

---

### User achievements

```http
GET|POST   /api/v1/users/user-achievements/
GET|PUT|PATCH|DELETE /api/v1/users/user-achievements/{id}/
```

**Model:** `users.UserAchievement` — achievements earned by a user.

| Field | Type | Notes |
|-------|------|-------|
| `user` | UUID | |
| `achievement` / `achievement_id` | object / int | |
| `earned_at` | datetime | Read-only, auto-set |

**Filters:** `achievement`, `user`  
**Scoped:** User sees only their achievements.

---

### Notifications

```http
GET|POST   /api/v1/users/notifications/
GET|PUT|PATCH|DELETE /api/v1/users/notifications/{uuid}/
```

**Model:** `users.Notification` — in-app notifications.

| Field | Type | Notes |
|-------|------|-------|
| `type` | enum | `STREAK`, `RECOMMENDATION`, `ACHIEVEMENT`, `SYSTEM`, `REVISION_DUE` |
| `title` | string | Max 160 chars |
| `body` | text | |
| `data` | JSON | Arbitrary payload |
| `read_at` | datetime | Null = unread |

**Filters:** `type`, `user`, `read_at`  
**Search:** `title`, `body`  
**Scoped:** User sees only their notifications.

---

## Content catalog

Base path: `/api/v1/` (root router)

### Subjects

```http
GET|POST   /api/v1/subjects/
GET|PUT|PATCH|DELETE /api/v1/subjects/{id}/
```

**Model:** `apis.Subject` — top-level subject (e.g. Physics).

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Max 40 chars |
| `slug` | string | Unique |
| `order_index` | smallint | Display order |

**Filters:** `slug`  
**Search:** `name`, `slug`  
**Ordering:** `order_index`, `name`, `id`

---

### Chapters

```http
GET|POST   /api/v1/chapters/
GET|PUT|PATCH|DELETE /api/v1/chapters/{id}/
```

**Model:** `apis.Chapter` — chapter within a subject.

| Field | Type | Notes |
|-------|------|-------|
| `subject` / `subject_id` | object / int | Nested read, ID write |
| `name` | string | |
| `slug` | string | Unique per subject |
| `order_index` | smallint | |

**Filters:** `subject`, `slug`  
**Search:** `name`, `slug`  
**Ordering:** `order_index`, `name`, `id`

---

### Concepts

```http
GET|POST   /api/v1/concepts/
GET|PUT|PATCH|DELETE /api/v1/concepts/{id}/
```

**Model:** `apis.Concept` — concept within a chapter.

| Field | Type | Notes |
|-------|------|-------|
| `chapter` / `chapter_id` | object / int | |
| `name` | string | |
| `slug` | string | Unique per chapter |
| `order_index` | smallint | |

**Filters:** `chapter`, `slug`  
**Search:** `name`, `slug`  
**Ordering:** `order_index`, `name`, `id`

---

### Concept prerequisites

```http
GET|POST   /api/v1/concept-prerequisites/
GET|PUT|PATCH|DELETE /api/v1/concept-prerequisites/{id}/
```

**Model:** `apis.ConceptPrerequisite` — prerequisite graph edges between concepts.

| Field | Type | Notes |
|-------|------|-------|
| `concept` / `concept_id` | object / int | The concept that requires a prerequisite |
| `prerequisite_concept` / `prerequisite_concept_id` | object / int | The prerequisite concept |

**Filters:** `concept`, `prerequisite_concept`

---

### Content items

```http
GET|POST   /api/v1/content-items/
GET|PUT|PATCH|DELETE /api/v1/content-items/{uuid}/
```

**Model:** `apis.ContentItem` — questions, theory, PYQs, solved examples.

| Field | Type | Notes |
|-------|------|-------|
| `content_type` | enum | `THEORY`, `SOLVED_EXAMPLE`, `PRACTICE_QUESTION`, `PYQ` |
| `subject_id`, `chapter_id`, `primary_concept_id` | int | Write-only FKs |
| `source_book` | enum | `HCV`, `DC_PANDEY`, `IRODOV`, `PYQ` |
| `difficulty` | smallint | 1–5 |
| `question_type` | enum | `SCQ`, `MCQ`, `NUMERICAL`, `ASSERTION_REASON`, `COMPREHENSION` |
| `jee_year` | smallint | For PYQs |
| `exam_type` | enum | `MAINS`, `ADVANCED` |
| `target_exam` | enum | `JEE_MAINS`, `JEE_ADVANCED`, `BOTH` |
| `has_diagram` | boolean | |
| `diagram_image_key`, `solution_image_key` | string | Storage keys |
| `is_active` | boolean | |
| `vector_id`, `external_row_id` | string | Search / embedding metadata |

**Filters:** `content_type`, `subject`, `chapter`, `primary_concept`, `source_book`, `question_type`, `exam_type`, `target_exam`, `is_active`, `has_diagram`, `difficulty`  
**Search:** `vector_id`, `external_row_id`, `page_number`  
**Ordering:** `created_at`, `difficulty`, `jee_year`

---

### Content secondary concepts

```http
GET|POST   /api/v1/content-secondary-concepts/
GET|PUT|PATCH|DELETE /api/v1/content-secondary-concepts/{id}/
```

**Model:** `apis.ContentSecondaryConcept` — additional concepts tagged on a content item (M2M join table).

| Field | Type | Notes |
|-------|------|-------|
| `content_item` | UUID | |
| `concept` | int | |

**Filters:** `content_item`, `concept`

---

### Content flags

```http
GET|POST   /api/v1/content-flags/
GET|PUT|PATCH|DELETE /api/v1/content-flags/{uuid}/
```

**Model:** `apis.ContentFlag` — user-reported content issues.

| Field | Type | Notes |
|-------|------|-------|
| `content_item` | UUID | |
| `reported_by` | UUID | Auto-set to current user on create |
| `reason` | string | Max 280 chars |
| `status` | enum | `OPEN`, `TRIAGED`, `RESOLVED`, `DISMISSED` |
| `resolved_by` | UUID | Staff reviewer |
| `resolved_at` | datetime | |

**Filters:** `status`, `content_item`, `reported_by`, `resolved_by`  
**Search:** `reason`  
**Scoped:** Users see flags they reported (staff sees all).

---

## Chat & study sessions

Base path: `/api/v1/chat/`

### Schema-based endpoints (PDF)

These map directly to the database schema (`study_sessions`, `conversations`, `messages`, `message_concepts`).

#### Study sessions

```http
GET|POST   /api/v1/chat/study-sessions/
GET|PUT|PATCH|DELETE /api/v1/chat/study-sessions/{uuid}/
```

**Model:** `chatbot.StudySession`

| Field | Type | Notes |
|-------|------|-------|
| `user` | UUID | Auto-set on create |
| `type` | enum | `DOUBT`, `PRACTICE`, `DIAGNOSTIC`, `REVISION`, `MOCK` |
| `started_at` | datetime | Auto-set |
| `ended_at` | datetime | |
| `duration_seconds` | int | |

**Filters:** `type`, `user`  
**Ordering:** `started_at`, `ended_at`  
**Scoped:** User sees only their sessions.

---

#### Conversations

```http
GET|POST   /api/v1/chat/conversations/
GET|PUT|PATCH|DELETE /api/v1/chat/conversations/{uuid}/
```

**Model:** `chatbot.Conversation` — a doubt/practice conversation thread.

| Field | Type | Notes |
|-------|------|-------|
| `user` | UUID | |
| `study_session` | UUID | Optional link to study session |
| `title` | string | |
| `source_content_item` / `source_content_item_id` | object / UUID | Question that started the conversation |
| `created_at` | datetime | |

**Filters:** `user`, `study_session`  
**Search:** `title`  
**Scoped:** User sees only their conversations.

---

#### Conversation messages

```http
GET|POST   /api/v1/chat/conversation-messages/
GET|PUT|PATCH|DELETE /api/v1/chat/conversation-messages/{uuid}/
```

**Model:** `chatbot.ConversationMessage` (DB table: `messages`)

| Field | Type | Notes |
|-------|------|-------|
| `conversation` | UUID | |
| `role` | enum | `user`, `assistant`, `system` |
| `content` | text | Message body |
| `retrieved_content_ids` | text | RAG retrieval IDs |
| `model` | string | LLM model name |
| `metadata` | JSON | Extra LLM metadata |
| `created_at` | datetime | |

**Filters:** `conversation`, `role`  
**Search:** `content`  
**Scoped:** User sees messages in their own conversations.

---

#### Message concepts

```http
GET|POST   /api/v1/chat/message-concepts/
GET|PUT|PATCH|DELETE /api/v1/chat/message-concepts/{id}/
```

**Model:** `chatbot.MessageConcept` — concepts linked to a message.

| Field | Type | Notes |
|-------|------|-------|
| `message` | UUID | |
| `concept` / `concept_id` | object / int | |
| `relation` | enum | `IN_RESPONSE`, `PREREQUISITE` |

**Filters:** `message`, `concept`, `relation`  
**Scoped:** User sees concepts for messages in their conversations.

---

### Legacy LLM chat endpoints (backward compatible)

These predate the schema models and power the live LLM study session UI. **Not removed** — existing clients should keep using them.

#### List / create chat sessions

```http
GET  /api/v1/chat/sessions/
POST /api/v1/chat/sessions/
```

**Model:** `chatbot.ChatSession` (legacy)

**GET:** Paginated list of the user's past sessions (newest first).

**POST body:**

```json
{
  "title": "Torque problem",
  "subject": "Physics",
  "active_chapters": ["laws_of_motion"]
}
```

Creates a new active session. Automatically ends any previously active session for the user.

**Response fields:** `id`, `title`, `subject`, `active_chapters`, `started_at`, `ended_at`, `is_active`

---

#### Session detail / delete

```http
GET    /api/v1/chat/sessions/{session_id}/
DELETE /api/v1/chat/sessions/{session_id}/
```

**GET:** Session detail with full nested `messages` array (including `concept_snapshots`).

**DELETE:** Hard-deletes the session and all messages.

---

#### End session

```http
PATCH /api/v1/chat/sessions/{session_id}/end/
```

Sets `is_active=false` and `ended_at` to the current time.

---

#### List / send messages (LLM hot path)

```http
GET  /api/v1/chat/sessions/{session_id}/messages/
POST /api/v1/chat/sessions/{session_id}/messages/
```

**GET:** Paginated message history for the session.

**POST body:**

```json
{
  "content": "A block of mass 2 kg is on a frictionless surface..."
}
```

**What happens on POST:**

1. Saves user `ChatMessage`
2. Calls Groq LLM (`ChatLLMService`) with session history
3. Saves assistant `ChatMessage` with structured JSON (`filling_gap`, `solution_steps`, `insight`, `try_next`, `concepts_mentioned`, `prerequisite_chain`)
4. Creates `ConceptSnapshot` rows for concepts mentioned
5. Fires `concept_mentioned` signal → updates analytics `ConceptProficiency` and `StudyStreak`

**Response:** Serialized assistant message with `concept_snapshots`.

---

#### Stream assistant reply (SSE)

```http
GET /api/v1/chat/sessions/{session_id}/messages/{msg_id}/stream/
```

**Auth required:** Yes (or dev mode)

Returns Server-Sent Events streaming the assistant reply token-by-token. `msg_id` must be a **user** message ID. Streams tokens from the corresponding assistant message.

**Event format:**

```
data: {"token": "The"}
data: {"token": "torque"}
data: {"done": true, "message": { ... full message object ... }}
```

---

#### Session concept snapshots

```http
GET /api/v1/chat/sessions/{session_id}/concepts/
```

Returns aggregated concept data for the session (average scores, latest trend, prerequisite flags) for the right-panel UI.

---

## Analytics & learning progress

Base path: `/api/v1/analytics/`

### Dashboard (aggregated UI payload)

```http
GET /api/v1/analytics/dashboard/
```

**Auth required:** Yes (or dev mode)

**What it does:** Returns a single payload for the Dashboard page:

- Overall proficiency % and attempted concept count
- Weak concepts list (score &lt; 50)
- Session streak with 7-day dot indicators
- Per-chapter concept health cards (Laws of Motion, Work Energy & Power, Rotational Motion)

Seeds default demo metrics if the user has no `ConceptProficiency` rows yet.

**Not a CRUD endpoint** — read-only aggregated view.

---

### Schema-based analytics (PDF)

#### Concept masteries

```http
GET|POST   /api/v1/analytics/concept-masteries/
GET|PUT|PATCH|DELETE /api/v1/analytics/concept-masteries/{id}/
```

**Model:** `analytics.ConceptMastery` — per-user mastery on schema `concept_mastery` table.

| Field | Type | Notes |
|-------|------|-------|
| `user`, `concept_id` | UUID, int | Unique together |
| `mastery_score` | decimal | 0–100 |
| `status` | enum | `NOT_STARTED`, `LEARNING`, `WEAK`, `PROFICIENT`, `MASTERED` |
| `is_flagged_weak` | boolean | |
| `total_attempts`, `correct_attempts` | int | |
| `last_practiced_at` | datetime | |

**Filters:** `status`, `is_flagged_weak`, `user`, `concept`  
**Scoped:** User sees only their rows.

---

#### Chapter progress

```http
GET|POST   /api/v1/analytics/chapter-progress/
GET|PUT|PATCH|DELETE /api/v1/analytics/chapter-progress/{id}/
```

**Model:** `analytics.ChapterProgress`

| Field | Type | Notes |
|-------|------|-------|
| `user`, `chapter_id` | | Unique together |
| `mastery_score` | decimal | |
| `completion_percent` | decimal | |

**Filters:** `chapter`, `user`

---

#### Proficiency snapshots

```http
GET|POST   /api/v1/analytics/proficiency-snapshots/
GET|PUT|PATCH|DELETE /api/v1/analytics/proficiency-snapshots/{id}/
```

**Model:** `analytics.ProficiencySnapshot` — daily subject-level proficiency (schema table `proficiency_snapshots`).

| Field | Type | Notes |
|-------|------|-------|
| `user`, `subject_id`, `snapshot_date` | | Unique together |
| `proficiency` | decimal | |

**Filters:** `subject`, `snapshot_date`, `user`  
**Ordering:** `snapshot_date`, `proficiency`

---

#### Learning gaps

```http
GET|POST   /api/v1/analytics/learning-gaps/
GET|PUT|PATCH|DELETE /api/v1/analytics/learning-gaps/{uuid}/
```

**Model:** `analytics.LearningGap` — detected weak areas.

| Field | Type | Notes |
|-------|------|-------|
| `concept_id` | int | |
| `severity` | smallint | |
| `source` | enum | Session type that detected the gap |
| `detected_at` | datetime | Auto-set |
| `resolved_at` | datetime | Null = open |

**Filters:** `severity`, `source`, `user`, `concept`

---

#### Recommendations

```http
GET|POST   /api/v1/analytics/recommendations/
GET|PUT|PATCH|DELETE /api/v1/analytics/recommendations/{uuid}/
```

**Model:** `analytics.Recommendation` — next-step suggestions for the learner.

| Field | Type | Notes |
|-------|------|-------|
| `type` | enum | `NEXT_QUESTION`, `REVISE_CONCEPT`, `LEARN_PREREQUISITE`, `PRACTICE_WEAK` |
| `concept_id`, `content_item_id` | | Optional targets |
| `reason` | string | |
| `score` | decimal | Ranking score |
| `served_at`, `dismissed_at` | datetime | |

**Filters:** `type`, `user`, `concept`, `content_item`  
**Search:** `reason`

---

#### Question attempts

```http
GET|POST   /api/v1/analytics/question-attempts/
GET|PUT|PATCH|DELETE /api/v1/analytics/question-attempts/{uuid}/
```

**Model:** `analytics.QuestionAttempt` — schema `question_attempts` table.

| Field | Type | Notes |
|-------|------|-------|
| `content_item_id` | UUID | |
| `study_session` | UUID | Optional |
| `submitted_answer` | JSON | |
| `is_correct` | boolean | |
| `error_type` | enum | `CONCEPTUAL_GAP`, `CALCULATION_ERROR`, `MISINTERPRETATION`, `PROCEDURAL_SLIP` |
| `time_taken_seconds` | int | |
| `hint_used` | boolean | |
| `attempt_number` | smallint | |
| `attempted_at` | datetime | |

**Filters:** `is_correct`, `error_type`, `user`, `content_item`, `study_session`

---

#### Streaks (schema)

```http
GET|POST   /api/v1/analytics/streaks/
GET|PUT|PATCH|DELETE /api/v1/analytics/streaks/{user_id}/
```

**Model:** `analytics.Streak` — schema `streaks` table (PK = `user_id`).

| Field | Type | Notes |
|-------|------|-------|
| `current_streak` | smallint | |
| `longest_streak` | smallint | |
| `last_active_date` | date | |

**Lookup:** `user_id`

---

#### Daily activities

```http
GET|POST   /api/v1/analytics/daily-activities/
GET|PUT|PATCH|DELETE /api/v1/analytics/daily-activities/{id}/
```

**Model:** `analytics.DailyActivity`

| Field | Type | Notes |
|-------|------|-------|
| `activity_date` | date | Unique per user per day |
| `minutes_studied` | smallint | |
| `questions_attempted` | smallint | |
| `doubts_asked` | smallint | |
| `goal_met` | boolean | |

**Filters:** `activity_date`, `goal_met`, `user`

---

#### Assessments

```http
GET|POST   /api/v1/analytics/assessments/
GET|PUT|PATCH|DELETE /api/v1/analytics/assessments/{uuid}/
```

**Model:** `analytics.Assessment`

| Field | Type | Notes |
|-------|------|-------|
| `type` | enum | `DIAGNOSTIC`, `CHAPTER_TEST`, `MOCK` |
| `chapter_id`, `concept_id` | int | Optional scope |
| `total_questions` | smallint | |
| `score`, `max_score` | decimal | |
| `status` | enum | `IN_PROGRESS`, `COMPLETED`, `ABANDONED` |
| `started_at`, `completed_at` | datetime | |

**Filters:** `type`, `status`, `user`, `chapter`, `concept`

---

#### Assessment questions

```http
GET|POST   /api/v1/analytics/assessment-questions/
GET|PUT|PATCH|DELETE /api/v1/analytics/assessment-questions/{uuid}/
```

**Model:** `analytics.AssessmentQuestion`

| Field | Type | Notes |
|-------|------|-------|
| `assessment` | UUID | |
| `content_item_id` | UUID | |
| `step_index` | smallint | Order in assessment |
| `submitted_answer` | JSON | |
| `is_correct` | boolean | |
| `error_type` | enum | |
| `hint_shown` | boolean | |
| `retries_count` | smallint | |
| `is_flagged` | boolean | |
| `answered_at` | datetime | |

**Filters:** `assessment`, `content_item`, `is_correct`, `is_flagged`  
**Scoped:** User sees questions for their own assessments.

---

### Legacy analytics endpoints

These use older models (string-based concept names, not schema FKs). Kept for backward compatibility with the chatbot signal handler and dashboard.

#### Concept proficiencies (legacy)

```http
GET|POST   /api/v1/analytics/concept-proficiencies/
GET|PUT|PATCH|DELETE /api/v1/analytics/concept-proficiencies/{id}/
```

**Model:** `analytics.ConceptProficiency` — string `concept_name` + `chapter`, updated by chatbot `concept_mentioned` signal.

**Filters:** `chapter`, `trend`, `user`  
**Search:** `concept_name`, `chapter`

---

#### Study streaks (legacy)

```http
GET|POST   /api/v1/analytics/study-streaks/
GET|PUT|PATCH|DELETE /api/v1/analytics/study-streaks/{id}/
```

**Model:** `analytics.StudyStreak` — updated by chatbot signals. Used by dashboard streak card.

---

#### Daily proficiency snapshots (legacy)

```http
GET|POST   /api/v1/analytics/daily-proficiency-snapshots/
GET|PUT|PATCH|DELETE /api/v1/analytics/daily-proficiency-snapshots/{id}/
```

**Model:** `analytics.DailyProficiencySnapshot` — chapter string + date averages.

---

#### Practice attempts (legacy)

```http
GET|POST   /api/v1/analytics/practice-attempts/
GET|PUT|PATCH|DELETE /api/v1/analytics/practice-attempts/{id}/
```

**Model:** `analytics.PracticeAttempt` — practice page attempts with string concept/chapter.

**Filters:** `chapter`, `question_type`, `is_correct`, `mistake_type`, `user`

---

#### Weekly improvements (legacy)

```http
GET|POST   /api/v1/analytics/weekly-improvements/
GET|PUT|PATCH|DELETE /api/v1/analytics/weekly-improvements/{id}/
```

**Model:** `analytics.WeeklyImprovement` — most-improved concept tracking.

**Filters:** `week_start`, `user`  
**Search:** `concept_name`

---

## Quick endpoint index

| Resource | Base path |
|----------|-----------|
| Health | `/health/` |
| JWT token | `/auth/token/` |
| JWT refresh | `/auth/token/refresh/` |
| Users | `/users/` |
| OAuth accounts | `/users/oauth-accounts/` |
| Auth sessions | `/users/auth-sessions/` |
| Student profiles | `/users/student-profiles/` |
| Preferences | `/users/preferences/` |
| Plans | `/users/plans/` |
| Subscriptions | `/users/subscriptions/` |
| Achievements | `/users/achievements/` |
| User achievements | `/users/user-achievements/` |
| Notifications | `/users/notifications/` |
| Subjects | `/subjects/` |
| Chapters | `/chapters/` |
| Concepts | `/concepts/` |
| Concept prerequisites | `/concept-prerequisites/` |
| Content items | `/content-items/` |
| Content secondary concepts | `/content-secondary-concepts/` |
| Content flags | `/content-flags/` |
| Study sessions (schema) | `/chat/study-sessions/` |
| Conversations | `/chat/conversations/` |
| Conversation messages | `/chat/conversation-messages/` |
| Message concepts | `/chat/message-concepts/` |
| Chat sessions (legacy LLM) | `/chat/sessions/` |
| Dashboard | `/analytics/dashboard/` |
| Concept masteries | `/analytics/concept-masteries/` |
| Chapter progress | `/analytics/chapter-progress/` |
| Proficiency snapshots | `/analytics/proficiency-snapshots/` |
| Learning gaps | `/analytics/learning-gaps/` |
| Recommendations | `/analytics/recommendations/` |
| Question attempts | `/analytics/question-attempts/` |
| Streaks | `/analytics/streaks/` |
| Daily activities | `/analytics/daily-activities/` |
| Assessments | `/analytics/assessments/` |
| Assessment questions | `/analytics/assessment-questions/` |
| Concept proficiencies (legacy) | `/analytics/concept-proficiencies/` |
| Study streaks (legacy) | `/analytics/study-streaks/` |
| Daily proficiency snapshots (legacy) | `/analytics/daily-proficiency-snapshots/` |
| Practice attempts (legacy) | `/analytics/practice-attempts/` |
| Weekly improvements (legacy) | `/analytics/weekly-improvements/` |

---

## Example: full request flow

### 1. Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"email": "student@example.com", "password": "secret"}'
```

### 2. Create a study session

```bash
curl -X POST http://localhost:8000/api/v1/chat/study-sessions/ \
  -H "Authorization: Bearer <access>" \
  -H "Content-Type: application/json" \
  -d '{"type": "DOUBT"}'
```

### 3. Start a conversation

```bash
curl -X POST http://localhost:8000/api/v1/chat/conversations/ \
  -H "Authorization: Bearer <access>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Torque on a beam", "study_session": "<session_uuid>"}'
```

### 4. Log a question attempt

```bash
curl -X POST http://localhost:8000/api/v1/analytics/question-attempts/ \
  -H "Authorization: Bearer <access>" \
  -H "Content-Type: application/json" \
  -d '{
    "content_item_id": "<content_uuid>",
    "submitted_answer": {"selected": "B"},
    "is_correct": false,
    "error_type": "CONCEPTUAL_GAP",
    "time_taken_seconds": 83
  }'
```

### 5. Fetch dashboard

```bash
curl http://localhost:8000/api/v1/analytics/dashboard/ \
  -H "Authorization: Bearer <access>"
```

---

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CHATBOT_AUTH_DISABLED` | `false` | Allow unauthenticated chat/analytics dev access |
| `CHATBOT_DEV_EMAIL` | `chatbot-dev@local.test` | Dev user email when auth disabled |
| `GROQ_API_KEY` | — | Required for legacy LLM chat POST |
| `CORS_ALLOWED_ORIGINS` | `localhost:3000` | Frontend origins |
