"""Fetch the latest committed prompt version from Opik and run it via litellm"""

import litellm
import opik
from version import PROMPT_NAME, get_latest
from config import DRY_RUN, OPIK_PROJECT_NAME, LLM_MODEL

USER_QUERY = "Should I put my savings in Bitcoin or index funds?"

@opik.track(project_name=OPIK_PROJECT_NAME)
def run_inference(system_prompt: str, user_query: str) -> str:
    response = litellm.completion(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ],
    )
    return response.choices[0].message.content

def main() -> None:
    if DRY_RUN:
        print(
            f"[DRY RUN] Opik creds not set — would fetch the latest '{PROMPT_NAME}' commit and "
            f"run it via litellm ({LLM_MODEL}) on:"
        )
        print(f"  {USER_QUERY}")
        return

    opik_client = opik.Opik()
    prompt = get_latest(opik_client)
    print(f"Using '{PROMPT_NAME}' commit {prompt.commit}")

    answer = run_inference(prompt.prompt, USER_QUERY)
    print(f"\n{answer}")

if __name__ == "__main__":
    main()