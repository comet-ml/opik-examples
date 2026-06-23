from . import config

SYSTEM_PROMPT = (
    "You are a race engineer's assistant. Using only the provided Formula 1 team-radio "
    "messages, answer the question with a concise, factual summary. Do not invent events "
    "that are not present in the messages. If the messages do not contain the answer, say so."
)

# ChatPrompt uses single-brace {field} placeholders that bind to dataset item fields.
USER_TEMPLATE = "Question: {query}\n\nRadio messages:\n{messages_text}"


def user_prompt(query: str, context_text: str) -> str:
    return USER_TEMPLATE.format(query=query, messages_text=context_text)


def promote(client, optimization_result):
    """Save the optimised prompt to the Opik Prompt Library (re-using the name versions it)."""
    return client.create_chat_prompt(
        name=config.PROMPT_NAME,
        messages=optimization_result.prompt.get_messages(),
        change_description=f"optimised score {optimization_result.score:.3f}",
        tags=["optimised", "f1-radio"],
    )
