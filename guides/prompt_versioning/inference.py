"""Fetch the latest committed prompt version from Opik and run it with the OpenAI SDK"""

import os
import opik
from openai import OpenAI
from version import DRY_RUN, OPIK_PROJECT_NAME, PROMPT_NAME, get_latest

from dotenv import load_dotenv
load_dotenv()

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
USER_QUERY = "Should I put my savings in Bitcoin or index funds?"

@opik.track(project_name=OPIK_PROJECT_NAME)
def run_inference(client: OpenAI, system_prompt: str, user_query: str) -> str:
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
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
            f"run it via OpenAI ({OPENAI_MODEL}) on:"
        )
        print(f"  {USER_QUERY}")
        return

    opik_client = opik.Opik()
    prompt = get_latest(opik_client)
    print(f"Using '{PROMPT_NAME}' commit {prompt.commit}")

    if not os.environ.get("OPENAI_API_KEY"):
        print("[DRY RUN] OPENAI_API_KEY not set — skipping the live OpenAI call.")
        return

    openai_client = OpenAI()
    answer = run_inference(openai_client, prompt.prompt, USER_QUERY)
    print(f"\n{answer}")

if __name__ == "__main__":
    main()