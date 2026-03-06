from openai import AsyncOpenAI
from app.config import settings
from app.logging_config import logger
from app.prompt import SYSTEM_PROMPT

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None


async def analyze_event(event_text: str) -> str:
    """Analyze an event using OpenAI. Returns analysis text or error message."""
    if not client:
        return "[OpenAI not configured] Provide OPENAI_API_KEY to enable AI analysis."

    try:
        resp = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=0.2,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Analyze this event and return structured operational guidance:\n\n{event_text}",
                },
            ],
        )
        return resp.choices[0].message.content or "[No response from model]"

    except Exception as e:
        error_type = type(e).__name__
        logger.error("OpenAI API error (%s): %s", error_type, str(e)[:200])

        if "insufficient_quota" in str(e):
            return f"[OpenAI quota exceeded] Add billing credits at platform.openai.com to enable analysis."
        if "invalid_api_key" in str(e):
            return f"[OpenAI auth error] API key is invalid. Check OPENAI_API_KEY."

        return f"[OpenAI error: {error_type}] {str(e)[:200]}"
