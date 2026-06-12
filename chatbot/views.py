"""
VIEWS — chatbot app
===================
No implementation yet. See models.py for the full schema and endpoint list.

Planned ViewSets / APIViews (Django REST Framework):

ChatSessionViewSet  (ModelViewSet)
  - list()      GET    /api/v1/chat/sessions/
  - create()    POST   /api/v1/chat/sessions/
  - retrieve()  GET    /api/v1/chat/sessions/{id}/
  - end()       PATCH  /api/v1/chat/sessions/{id}/end/
  - destroy()   DELETE /api/v1/chat/sessions/{id}/

ChatMessageViewSet
  - list()    GET  /api/v1/chat/sessions/{id}/messages/
  - create()  POST /api/v1/chat/sessions/{id}/messages/
              Steps:
                1. Save user ChatMessage
                2. Fetch history + student proficiency from analytics
                3. Call Anthropic API (tool_use for structured JSON output)
                4. Save assistant ChatMessage + ConceptSnapshot rows
                5. Fire concept_updated signal → analytics recalculates scores
                6. Return serialized assistant message
  - stream()  GET  /api/v1/chat/sessions/{id}/messages/{msg_id}/stream/
              Server-Sent Events for token streaming

ConceptSnapshotView
  - GET /api/v1/chat/sessions/{id}/concepts/
    Aggregates ConceptSnapshot rows — used for right-panel UI + session summary

Key implementation notes:
  - LLM call should be async (asyncio or Celery task) on non-streaming path
  - Rate-limit with DRF throttling (50 msg/hour per user)
  - All views: IsAuthenticated + IsOwner (users can only access their own sessions)
"""

from django.shortcuts import render

# Views will be implemented here.
