# TODO: replace these with the prompt your use case actually needs.
SYSTEM_PROMPT = (
    "You are a helpful assistant. Using only the provided context, answer the request with a "
    "concise, factual response. Do not invent details that are not present in the context. "
    "If the context does not contain the answer, say so."
)

# ChatPrompt uses single-brace {field} placeholders that bind to dataset item fields.
USER_TEMPLATE = "Request: {input}\n\nContext:\n{context_text}"


def user_prompt(request: str, context_text: str) -> str:
    return USER_TEMPLATE.format(input=request, context_text=context_text)


def promote(client, optimization_result):
    """Save the optimised prompt to the Opik Prompt Library (re-using the name versions it)."""
    from . import config

    return client.create_chat_prompt(
        name=config.PROMPT_NAME,
        messages=optimization_result.prompt.get_messages(),
        change_description=f"optimised score {optimization_result.score:.3f}",
        tags=["optimised", "example-use-case"],
    )
