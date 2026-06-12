"""
chatbot/serializers.py
======================
Serializers for the chatbot app.

PLANNED SERIALIZERS
-------------------

ChatSessionSerializer
  - Fields: id, title, subject, active_chapters, started_at, ended_at, is_active
  - Read-only output for list and detail views

CreateChatSessionSerializer
  - Fields: subject, active_chapters (optional — defaults from StudentProfile)
  - Creates a new ChatSession for the requesting user

ConceptSnapshotSerializer
  - Fields: concept_name, score_at_time, trend, is_prerequisite

ChatMessageSerializer
  - Fields: id, role, content, structured_response, tokens_used, latency_ms, created_at
  - Nested: concept_snapshots (list of ConceptSnapshotSerializer)
  - Read-only; returned after LLM processes the message

SendMessageSerializer  (input only)
  - Fields: content (the user's question text)
  - Validates: content is not blank, session is active
  - On save: triggers LLM call, returns ChatMessageSerializer of assistant reply

ChatSessionDetailSerializer
  - Extends ChatSessionSerializer
  - Nested: messages (list of ChatMessageSerializer, ordered by created_at)
"""

# Serializers will be implemented here.
