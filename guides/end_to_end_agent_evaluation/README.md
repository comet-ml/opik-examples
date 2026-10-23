# End-to-end agent evaluation

Evaluate an LLM agent across its whole lifecycle with Opik: trace it, build a baseline from error analysis, define judges once, align them with humans, gate the release, then reuse the same judges online and close the loop.

## What this does

Evaluating an agent is not a one-time "does it pass?" check; it is a loop. This notebook teaches that loop on one small RAG + tool-using billing-support agent for a fictional product (Acme Cloud). Before production you score a curated golden dataset and gate the release (offline evaluation); after production you score live traces with the same judges, record guardrail hits, and promote failures back into the dataset (online evaluation). The spine of the guide is **one judge, two harnesses**: the grounding judge is defined once as a constant and runs both as an offline experiment metric and as an online evaluation rule, so production quality and the release gate use the same yardstick.

## Prerequisites

```bash
uv sync    # or: pip install "opik>=2.2.72" openai matplotlib ipywidgets
```

| Variable | Description |
|---|---|
| `OPIK_API_KEY` | Opik API key |
| `OPIK_WORKSPACE` | Opik workspace name |
| `OPIK_URL_OVERRIDE` | Optional; set for a self-hosted Opik deployment |
| `OPENAI_API_KEY` | OpenAI key; the agent uses `gpt-4o-mini` and the judges use `gpt-4o` |

If a variable is not set, the setup cells prompt for it (`opik.configure()` for Opik, `getpass` for the OpenAI key). There is **no dry-run**: the guide logs real traces, experiments, an annotation queue and an online rule to your workspace, and calls the OpenAI API. The online rule in Part C only scores traffic if your workspace has an LLM provider configured for online evaluation.

## Running it

```bash
uv sync
uv run --with jupyter jupyter lab
```

Then open a notebook and run the cells top to bottom:

| Notebook | What it covers | Colab |
|---|---|---|
| `end_to_end_agent_evaluation.ipynb` | The full guide: Parts A, B and C below | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/comet-ml/opik-examples/blob/main/guides/end_to_end_agent_evaluation/end_to_end_agent_evaluation.ipynb) |
| `agent_evaluation_quickstart.ipynb` | A 20-minute quickstart: observe the agent, define a judge once, run one experiment, align the judge with humans | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/comet-ml/opik-examples/blob/main/guides/end_to_end_agent_evaluation/agent_evaluation_quickstart.ipynb) |

## How it works

- **Setup:** registers the agent's system prompt as a versioned prompt in the [Prompt Library](https://www.comet.com/docs/opik/prompt_engineering/prompt_management) and links it to every trace.
- **Part A, foundations:** traces the agent with `@opik.track` (tool and LLM spans), then builds a golden dataset bottom-up from the failure modes found by reading traces.
- **Part B, before production:** defines heuristic, LLM-as-a-judge, G-Eval, custom, span-level and trajectory metrics; runs a baseline and a broken-retrieval candidate as [experiments](https://www.comet.com/docs/opik/evaluation/evaluate_your_llm); [aligns the grounding judge with human labels](https://www.comet.com/docs/opik/evaluation/judge_alignment) via an annotation queue and a TPR/TNR confusion matrix; and turns experiment aggregates into a pass/fail release gate.
- **Part C, after production:** creates an [online evaluation rule](https://www.comet.com/docs/opik/production/online-evaluation/rules) from the same grounding criteria, records guardrail verdicts on the trace for traceability, generates production-like traffic, and promotes low-scoring traces back into the golden dataset.
- **Recap:** a checklist for applying the loop to your own agent.
