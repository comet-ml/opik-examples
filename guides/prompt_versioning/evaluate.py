"""Score two prompt versions for hallucination using an Opik dataset + evaluate_prompt"""

import os
import opik
from opik.evaluation import evaluate_prompt
from opik.evaluation.metrics import Hallucination

from prompts import SUMMARIZER_V1, SUMMARIZER_V2
from version import DRY_RUN, OPIK_PROJECT_NAME

from dotenv import load_dotenv
load_dotenv()

SUMMARIZER_PROMPT_NAME = "summaryfintechv1"
DATASET_NAME = "prompt-versioning-scores"
JUDGE_MODEL = os.environ.get("OPIK_EXAMPLES_MODEL", "openai/gpt-5-mini")

TRANSCRIPT = (
    "Apple reported Q4 revenue of $89.5 billion, up 6% year-over-year. iPhone revenue grew "
    "10% to $43.8 billion. CEO Tim Cook said 'We're thrilled with the strong demand for "
    "iPhone 15 Pro.'"
)
CONTEXT = "Q4 revenue: $89.5B, +6% YoY. iPhone: $43.8B, +10%. Tim Cook commented on iPhone 15 Pro demand."
QUERY = f"Summarize this earnings call:\n{TRANSCRIPT}"

def build_dataset(client: opik.Opik) -> opik.Dataset:
    dataset = client.get_or_create_dataset(name=DATASET_NAME, project_name=OPIK_PROJECT_NAME)
    dataset.insert([{"input": QUERY, "context": CONTEXT}])
    return dataset

def score_version(dataset: opik.Dataset, prompt: opik.Prompt, experiment_name: str):
    return evaluate_prompt(
        dataset=dataset,
        messages=[
            {"role": "system", "content": prompt.prompt},
            {"role": "user", "content": "{{input}}"},
        ],
        model=JUDGE_MODEL,
        scoring_metrics=[Hallucination(model=JUDGE_MODEL)],
        experiment_name=experiment_name,
        prompt=prompt,
    )

def main() -> None:
    if DRY_RUN:
        print(
            "[DRY RUN] Opik creds not set — would score 2 versions of "
            f"'{SUMMARIZER_PROMPT_NAME}' on dataset '{DATASET_NAME}' with "
            f"Hallucination(model={JUDGE_MODEL}):"
        )
        print(f"  v1 (basic):  {SUMMARIZER_V1[:60]}...")
        print(f"  v2 (strict): {SUMMARIZER_V2[:60]}...")
        return

    client = opik.Opik()
    dataset = build_dataset(client)

    v1 = client.create_prompt(name=SUMMARIZER_PROMPT_NAME, prompt=SUMMARIZER_V1)
    v2 = client.create_prompt(name=SUMMARIZER_PROMPT_NAME, prompt=SUMMARIZER_V2)

    score_version(dataset, v1, "summarizer-v1-basic")
    score_version(dataset, v2, "summarizer-v2-strict")

    print("Experiments logged to Opik — compare the Hallucination scores for v1 vs v2 in the UI.")

if __name__ == "__main__":
    main()