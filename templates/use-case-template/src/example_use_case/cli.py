import typer

from . import config
from .data import load_cases

app = typer.Typer(add_completion=False, help="Example Opik use-case demo — the full eval loop.")


@app.command()
def run(input: str, context: list[str] = typer.Option(None, "--context", "-c")) -> None:
    """Run the app on a single input (traced in Opik when an LLM key is set)."""
    if not config.LLM_READY:
        typer.echo("[DRY RUN] ANTHROPIC_API_KEY not set — would run the app on:")
        typer.echo(f"  input: {input}")
        for line in context or []:
            typer.echo(f"  context: {line}")
        return
    from .app import run as run_app

    result = run_app({"input": input, "context": context or []})
    typer.echo(f"\nOutput:\n{result['output']}")


@app.command("eval")
def eval_cmd() -> None:
    """Create the Opik dataset + test suite and run evaluation (metrics + assertions)."""
    cases = load_cases()
    if config.DRY_RUN:
        typer.echo(
            "[DRY RUN] Opik creds not set. Would create dataset "
            f"'{config.DATASET_NAME}' and test suite '{config.SUITE_NAME}' with:"
        )
        for case in cases:
            typer.echo(f"  input: {case['input']}")
            for assertion in case["assertions"]:
                typer.echo(f"      assert: {assertion}")
        return
    from . import evaluation

    suite_result, _ = evaluation.run_eval(cases)
    typer.echo(f"Test-suite pass rate: {suite_result.pass_rate:.0%}")
    url = getattr(suite_result, "experiment_url", None)
    if url:
        typer.echo(f"Experiment: {url}")


@app.command()
def optimize() -> None:
    """Run Optimization Studio against the eval dataset to improve the prompt."""
    cases = load_cases()
    if config.DRY_RUN:
        typer.echo(
            "[DRY RUN] Would run MetaPromptOptimizer on prompt "
            f"'{config.PROMPT_NAME}' against dataset '{config.DATASET_NAME}'."
        )
        return
    import opik

    from . import evaluation, optimization

    client = opik.Opik()
    dataset = evaluation.build_dataset(client, cases)
    result = optimization.run_optimization(dataset)
    typer.echo(f"Score: {result.initial_score} -> {result.score}")
    link = result.get_run_link() if hasattr(result, "get_run_link") else None
    if link:
        typer.echo(f"Optimization run: {link}")


@app.command()
def promote() -> None:
    """Optimise the prompt and save the result to the Opik Prompt Library (versioned)."""
    cases = load_cases()
    if config.DRY_RUN:
        typer.echo(
            f"[DRY RUN] Would save optimised prompt '{config.PROMPT_NAME}' to the Opik Prompt Library."
        )
        return
    import opik

    from . import evaluation, optimization, prompts

    client = opik.Opik()
    dataset = evaluation.build_dataset(client, cases)
    result = optimization.run_optimization(dataset)
    prompts.promote(client, result)
    typer.echo(
        f"Saved prompt '{config.PROMPT_NAME}' to the Prompt Library (optimised score {result.score:.3f})."
    )


@app.command("run-all")
def run_all() -> None:
    """Run the full demo loop: eval -> optimize -> promote."""
    eval_cmd()
    optimize()
    promote()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
