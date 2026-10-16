"""Shared OpenAI helpers used by every AI call in the app.

No Streamlit imports here, so everything can be unit-tested on its own.

Two kinds of call:
  * structured_call - the model must return JSON matching a Pydantic schema
    (OpenAI Structured Outputs). Used for the form fill, answer review, risk matrix,
    recommendation, contract notes and summary.
  * chat_call - free-text answer to a conversation. Used for the follow-up Q&A.
"""

from openai import OpenAI

# Any chat model that supports Structured Outputs works here. Check OpenAI's current
# model list and change this if your assignment names a specific model.
MODEL = "gpt-4o-mini"


def structured_call(api_key: str, system: str, user: str, schema, max_attempts: int = 2, max_tokens: int = 6000):
    """Ask the model for an answer matching `schema` (a Pydantic model class).

    The SDK sends the schema to the model and parses the reply back into a `schema`
    object. If our own validators reject the reply, we retry once and tell the model
    what was wrong.
    """
    client = OpenAI(api_key=api_key)

    last_error = None
    for _ in range(max_attempts):
        message = user
        if last_error:
            message += f"\n\nYour previous answer was rejected: {last_error}. Fix this and resubmit."

        try:
            completion = client.chat.completions.parse(
                model=MODEL,
                max_completion_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": message},
                ],
                response_format=schema,
            )
        except ValueError as exc:  # pydantic.ValidationError is a ValueError
            last_error = str(exc)
            continue

        reply = completion.choices[0].message
        if reply.refusal:
            raise RuntimeError(f"The model declined to answer: {reply.refusal}")
        if reply.parsed is None:
            last_error = "no structured answer returned"
            continue
        return reply.parsed

    raise RuntimeError(f"Could not get a valid answer from the AI: {last_error}")


def chat_call(api_key: str, system: str, history: list[dict], max_tokens: int = 800) -> str:
    """Return the model's plain-text reply to a conversation.

    `history` is a list of {"role": "user" | "assistant", "content": "..."} messages.
    """
    client = OpenAI(api_key=api_key)
    completion = client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, *history],
    )
    text = completion.choices[0].message.content
    if not text or not text.strip():
        raise RuntimeError("The model returned an empty answer.")
    return text.strip()