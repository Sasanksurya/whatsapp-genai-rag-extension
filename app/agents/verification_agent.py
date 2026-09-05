"""
Verification Agent.

Checks a generated answer against the context it was supposedly
based on, and — critically — CORRECTS unsupported claims rather than
just flagging them. An earlier version only appended a warning note
to an answer that still contained hallucinated content, which isn't
actually "strictly grounded," just "grounded with a disclaimer."
This version re-grounds the answer itself when verification fails.
"""
from app.llm.groq_client import llm_gateway

VERIFY_SYSTEM_PROMPT = (
    "You are a strict fact-checker. Given a CONTEXT and an ANSWER, "
    "determine if every claim in the ANSWER is actually supported by "
    "the CONTEXT. Pay special attention to LISTS (e.g. skills, tools, "
    "projects) — every single listed item must appear in the CONTEXT, "
    "not just be plausible or typical for the role.\n"
    "Respond in exactly this format:\n"
    "VERDICT: SUPPORTED or UNSUPPORTED\n"
    "NOTE: <one short sentence, only if UNSUPPORTED — say what isn't backed up>"
)

CORRECT_SYSTEM_PROMPT = (
    "You are correcting an AI-generated answer that included claims not "
    "supported by the given CONTEXT. Rewrite the answer using ONLY "
    "information explicitly present in the CONTEXT. "
    "Remove any item, skill, fact, or claim that is not explicitly stated — "
    "do not keep it 'just in case' and do not soften it into a hedge. "
    "If removing unsupported claims leaves little or nothing left, say "
    "plainly that the document doesn't contain enough information to fully "
    "answer the question. Output ONLY the corrected answer, nothing else."
)


def verify_answer(answer: str, context: str) -> dict:
    if not context:
        # Nothing was retrieved — nothing to verify against
        return {"verified": True, "note": None}

    prompt = f"CONTEXT:\n{context}\n\nANSWER:\n{answer}"
    result = llm_gateway.generate(VERIFY_SYSTEM_PROMPT, prompt)

    verified = "VERDICT: SUPPORTED" in result.upper()
    note = None
    if not verified:
        for line in result.splitlines():
            if line.upper().startswith("NOTE:"):
                note = line.split(":", 1)[1].strip()
    return {"verified": verified, "note": note}


def correct_answer(answer: str, context: str, question: str) -> str:
    prompt = (
        f"CONTEXT:\n{context}\n\n"
        f"ORIGINAL QUESTION: {question}\n\n"
        f"AI ANSWER TO CORRECT:\n{answer}"
    )
    return llm_gateway.generate(CORRECT_SYSTEM_PROMPT, prompt).strip()
