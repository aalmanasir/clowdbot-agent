from openai import AsyncOpenAI
from app.config import settings
from app.prompt import SYSTEM_PROMPT

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

async def analyze_event(event_text: str) -> str:
    if not client:
        return "OpenAI not configured."

    resp = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Analyze this event and return structured operational guidance:\n\n{event_text}"
            }
        ]
    )
    return resp.choices[0].message.content or "No response."
