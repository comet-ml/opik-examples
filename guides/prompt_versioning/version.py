"""Prompt Versioning tracing using OPIK
Every call to `client.create_prompt` with the same `name` creates a new, immutable
version ("commit") of that prompt nothing is overwritten. `client.get_prompt` fetches a specific commit"""

import opik

from config import DRY_RUN
from prompts import FINTECH_ASSISTANT_V1, FINTECH_ASSISTANT_V2

PROMPT_NAME = "fintechassistv1"

def create_version(client: opik.Opik, prompt_text: str, tag: str) -> opik.Prompt:
    """Save a new version of PROMPT_NAME to the Prompt Library."""
    return client.create_prompt(name=PROMPT_NAME, prompt=prompt_text, metadata={"tag": tag})

def get_latest(client: opik.Opik) -> opik.Prompt:
    """Fetch the most recently committed version of PROMPT_NAME."""
    return client.get_prompt(name=PROMPT_NAME)

def get_version(client: opik.Opik, commit: str) -> opik.Prompt:
    """Fetch a specific commit of PROMPT_NAME."""
    return client.get_prompt(name=PROMPT_NAME, commit=commit)

def main() -> None:
    if DRY_RUN:
        print("[DRY RUN] Opik creds not set — would create 2 versions of prompt:")
        print(f"  name: {PROMPT_NAME}")
        print(f"  v1 tag=baseline             ({len(FINTECH_ASSISTANT_V1)} chars)")
        print(f"  v2 tag=compliance-reviewed  ({len(FINTECH_ASSISTANT_V2)} chars)")
        return

    client = opik.Opik()

    v1 = create_version(client, FINTECH_ASSISTANT_V1, tag="baseline")
    print(f"Created '{PROMPT_NAME}' commit {v1.commit} (tag=baseline)")

    v2 = create_version(client, FINTECH_ASSISTANT_V2, tag="compliance-reviewed")
    print(f"Created '{PROMPT_NAME}' commit {v2.commit} (tag=compliance-reviewed)")

    latest = get_latest(client)
    print(f"Latest version of '{PROMPT_NAME}' is commit {latest.commit}")

if __name__ == "__main__":
    main()
