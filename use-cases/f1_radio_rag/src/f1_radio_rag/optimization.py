from opik.evaluation.metrics import AnswerRelevance
from opik_optimizer import ChatPrompt, MetaPromptOptimizer

from . import config
from .prompts import SYSTEM_PROMPT, USER_TEMPLATE


def _relevance_metric(dataset_item: dict, llm_output: str) -> float:
    # Optimizer metrics are plain callables (dataset_item, llm_output) -> float.
    # We wrap Opik's AnswerRelevance LLM-judge so the optimiser scores against a real metric.
    result = AnswerRelevance(model=config.JUDGE_MODEL).score(
        input=dataset_item["query"],
        output=llm_output,
        context=dataset_item["messages"],
    )
    return result.value


_relevance_metric.__name__ = "answer_relevance"


def run_optimization(dataset):
    prompt = ChatPrompt(
        name=config.PROMPT_NAME,
        system=SYSTEM_PROMPT,
        user=USER_TEMPLATE,
        model=config.GEN_MODEL,
    )
    # skip_perfect_score=False so the optimiser runs every round even when the
    # baseline already scores high, instead of short-circuiting after the baseline.
    optimizer = MetaPromptOptimizer(model=config.OPTIMIZER_MODEL, n_threads=4, skip_perfect_score=False)
    return optimizer.optimize_prompt(
        prompt=prompt,
        dataset=dataset,
        metric=_relevance_metric,
        max_trials=12,
        n_samples=8,
    )
