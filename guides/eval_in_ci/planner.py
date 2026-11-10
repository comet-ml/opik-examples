"""The application under test: an LLM that turns a driving scenario into a JSON plan."""

# WHY: one module holds both the evaluation tasks and the production entry point, so the experiment
# and the traffic in Logs run the exact same model call.

import functools
from collections.abc import Callable, Sequence
from typing import Any

import opik

from config import ENV_PRODUCTION, GEN_MODEL, TRAFFIC_TAG
from scenarios import parse_plan


@functools.cache
def _tracked_completion() -> Callable[..., Any]:
    """litellm.completion wrapped so each call is an LLM span with tokens and cost."""
    import litellm
    from opik.integrations.litellm import track_completion

    return track_completion()(litellm.completion)


def build_messages(system_prompt: str, scenario: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": scenario},
    ]


def plan_text(system_prompt: str, scenario: str, *, completion: Callable[..., Any] | None = None) -> str:
    """Ask the model for a plan and return its raw text."""
    call = completion or _tracked_completion()
    # WHY: evaluate() aborts the whole run on any task error, so ride out transient rate limits.
    response = call(
        model=GEN_MODEL, messages=build_messages(system_prompt, scenario), temperature=0, num_retries=3
    )
    return response.choices[0].message.content or ""


def make_eval_task(
    system_prompt: str, *, completion: Callable[..., Any] | None = None
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Task for evaluate(): the parsed plan is what the sub-metrics score."""

    def task(item: dict[str, Any]) -> dict[str, Any]:
        text = plan_text(system_prompt, item["input"], completion=completion)
        return {"output": parse_plan(text), "raw_output": text}

    return task


# WHY: the test-suite assertion judge reads only "input" and "output", so return exactly those.
def make_suite_task(
    system_prompt: str, *, completion: Callable[..., Any] | None = None
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Task for run_tests(): the raw model text, so assertions can judge its format."""

    def task(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "input": item["input"],
            "output": plan_text(system_prompt, item["input"], completion=completion),
        }

    return task


# WHY: the online rule maps input.scenario and output.plan, and scores only traces with TRAFFIC_TAG.
@opik.track(name="scenario_planner", tags=[TRAFFIC_TAG], ignore_arguments=["client", "completion"])
def answer(
    scenario: str, prompt_name: str, *, client: Any, completion: Callable[..., Any] | None = None
) -> dict[str, Any]:
    """Production entry point: plan with whatever prompt version production points at."""
    prompt = client.get_prompt(prompt_name, environment=ENV_PRODUCTION)
    return {
        "plan": plan_text(prompt.prompt, scenario, completion=completion),
        "prompt_version": prompt.version,
    }


def simulate_traffic(
    client: Any, prompt_name: str, requests: Sequence[str], *, completion: Callable[..., Any] | None = None
) -> int:
    """Answer each request through the production entry point, then flush the traces."""
    for scenario in requests:
        answer(scenario, prompt_name, client=client, completion=completion)
    opik.flush_tracker()
    return len(requests)
