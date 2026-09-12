"""
LLM Gateway — Groq implementation.

This is intentionally the ONLY module that talks to the LLM provider.
Later phases (RAG Agent, Verification Agent, etc.) call `generate()`
here rather than importing the Groq SDK directly — that keeps the
provider swappable and makes context-minimization enforceable in
one place (see Phase 5: Security Hardening).
"""

from groq import Groq
from app.core.config import settings


class LLMGateway:
    def __init__(self) -> None:
        if not settings.groq_api_key:
            # Fail loudly at call-time, not at import-time, so the
            # rest of the app (health checks, docs) still works
            # without a key configured yet.
            self._client = None
        else:
            self._client = Groq(api_key=settings.groq_api_key)

    def is_configured(self) -> bool:
        return self._client is not None

    def generate(self, system_prompt: str, user_message: str) -> str:
        if self._client is None:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Get a free key at "
                "https://console.groq.com/keys and add it to your .env file."
            )

        completion = self._client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_message,
                },
            ],
            temperature=0.3,

            # GPT-OSS models use reasoning tokens as part of the
            # completion budget. Give the model enough room to
            # reason briefly and then produce the actual answer.
            max_completion_tokens=4096,

            # Low reasoning is sufficient for document Q&A and
            # prevents the model from spending the entire budget
            # on internal reasoning.
            reasoning_effort="low",

            # We only need the final answer in message.content.
            include_reasoning=False,
        )

        content = completion.choices[0].message.content

        print("\n===== GROQ RESPONSE DEBUG =====")
        print("MODEL:", settings.groq_model)
        print("FINISH REASON:", completion.choices[0].finish_reason)
        print("CONTENT:", repr(content))
        print("===============================\n")

        return content or ""


# Singleton — imported by agents/routes instead of instantiating per-request
llm_gateway = LLMGateway()