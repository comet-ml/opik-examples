import litellm
import opik

from . import config
from .prompts import SYSTEM_PROMPT, user_prompt


def _generate(request: str, context_text: str) -> str:
    response = litellm.completion(
        model=config.GEN_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(request, context_text)},
        ],
    )
    return response.choices[0].message.content


@opik.track(project_name=config.OPIK_PROJECT_NAME)
def run(item: dict) -> dict:
    # TODO: this is the deployed app. Replace the body with your real logic (retrieval,
    # tool use, multi-step chains, etc.). It must return input/output/context so the eval
    # metrics can score it.
    context = item.get("context", [])
    context_text = "\n".join(context)
    output = _generate(item["input"], context_text)
    return {"input": item["input"], "output": output, "context": context}
