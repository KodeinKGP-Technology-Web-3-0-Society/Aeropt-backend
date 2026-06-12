import json
import time

from django.conf import settings

from chatbot.models import ChatMessage


class ChatServiceError(Exception):
    pass


class ChatLLMService:
    def __init__(self):
        self.model = getattr(settings, "CHATBOT_MODEL", "gpt-4.1-mini")
        self.max_tokens = int(getattr(settings, "CHATBOT_MAX_TOKENS", 1000))
        self.api_key = getattr(settings, "OPENAI_API_KEY", "")
        self.response_schema = {
            "name": "prepwise_chat_response",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "assistant_text": {"type": "string"},
                    "filling_gap": {"type": "string"},
                    "solution_steps": {"type": "array", "items": {"type": "string"}},
                    "insight": {"type": "string"},
                    "try_next": {"type": "array", "items": {"type": "string"}},
                    "concepts_mentioned": {"type": "array", "items": {"type": "string"}},
                    "prerequisite_chain": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "concept": {"type": "string"},
                                "score": {"type": "integer", "minimum": 0, "maximum": 100},
                                "color": {"type": "string", "enum": ["red", "orange", "yellow", "green"]},
                            },
                            "required": ["concept", "score", "color"],
                        },
                    },
                },
                "required": [
                    "assistant_text",
                    "filling_gap",
                    "solution_steps",
                    "insight",
                    "try_next",
                    "concepts_mentioned",
                    "prerequisite_chain",
                ],
            },
        }

    def build_system_prompt(self, concept_scores):
        weak = [item for item in concept_scores if int(item.get("score", 0)) < 50]
        weak_lines = ", ".join(f"{item['concept_name']}({item['score']})" for item in weak[:15]) or "none"
        return (
            "You are a JEE Physics tutor. Return concise, stepwise help.\n"
            "Always return strict JSON with keys: filling_gap, solution_steps, insight, try_next, "
            "concepts_mentioned, prerequisite_chain, assistant_text.\n"
            "assistant_text must be the complete natural-language answer shown in the chat bubble.\n"
            f"Weak concepts: {weak_lines}."
        )

    def fetch_concept_scores(self, user):
        del user
        return []

    def _fallback_payload(self, user_text):
        return {
            "filling_gap": "Let's identify the core concept before solving.",
            "solution_steps": [
                "Write known values and what is asked.",
                "Choose the governing equation and substitute carefully.",
                "Check units and physical reasonableness.",
            ],
            "insight": "Focus on concept first; arithmetic comes later.",
            "try_next": [
                "What changes if one variable doubles?",
                "Can you solve the same question with an alternate method?",
            ],
            "concepts_mentioned": ["Physics Fundamentals"],
            "prerequisite_chain": [
                {"concept": "Physics Fundamentals", "score": 60, "color": "yellow"},
            ],
            "assistant_text": f"Let's solve this step by step: {user_text}",
        }

    def _parse_structured(self, raw_text):
        data = json.loads(raw_text)
        if not isinstance(data, dict):
            raise ChatServiceError("Model response JSON must be an object.")
        return data

    def generate_reply(self, user, session, history, user_text):
        concept_scores = self.fetch_concept_scores(user)
        system_prompt = self.build_system_prompt(concept_scores)

        if not self.api_key or self.api_key in {"sk-...", "your-openai-api-key"}:
            payload = self._fallback_payload(user_text)
            return {
                "assistant_text": payload.pop("assistant_text"),
                "structured": payload,
                "tokens_used": 0,
                "latency_ms": 0,
                "system_prompt": system_prompt,
            }

        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover
            raise ChatServiceError(f"OpenAI client import failed: {exc}") from exc

        start = time.perf_counter()
        client = OpenAI(api_key=self.api_key)
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            role = "assistant" if msg.role == ChatMessage.ROLE_ASSISTANT else "user"
            messages.append({"role": role, "content": msg.content})

        try:
            res = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": self.response_schema,
                },
            )
        except Exception as exc:
            raise ChatServiceError(f"OpenAI request failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - start) * 1000)
        raw_text = (res.choices[0].message.content or "").strip()
        if not raw_text:
            raise ChatServiceError("LLM returned empty response.")

        structured = self._parse_structured(raw_text)
        assistant_text = structured.get("assistant_text") or structured.get("insight") or "Here's the explanation."
        usage = getattr(res, "usage", None)
        in_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        out_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        return {
            "assistant_text": assistant_text,
            "structured": structured,
            "tokens_used": in_tokens + out_tokens,
            "latency_ms": latency_ms,
            "system_prompt": system_prompt,
        }
