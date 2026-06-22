import typer

from . import config, rag
from .data import load_eval_cases, load_radio_messages

app = typer.Typer(add_completion=False, help="F1 radio RAG demo — the full Opik 2.0 loop.")


@app.command()
def ingest() -> None:
    """Load synthetic team-radio messages into ChromaDB (offline)."""
    count = rag.ingest(load_radio_messages())
    typer.echo(f"Ingested {count} radio messages into ChromaDB collection '{config.COLLECTION}'.")


@app.command()
def ask(query: str, k: int = 5) -> None:
    """Retrieve relevant radio messages and summarise them with Claude."""
    context = rag.retrieve(query, k)
    if not context:
        typer.echo("No messages found — run `f1rag ingest` first.")
        raise typer.Exit(1)
    typer.echo("Retrieved messages:")
    for message in context:
        typer.echo(f"  - {message}")
    if not config.LLM_READY:
        typer.echo("\n[DRY RUN] ANTHROPIC_API_KEY not set — would summarise the above with Claude.")
        return
    result = rag.answer(query, k)
    typer.echo(f"\nSummary:\n{result['output']}")


@app.command("eval")
def eval_cmd() -> None:
    """Create the Opik dataset + test suite and run evaluation (metrics + assertions)."""
    cases = load_eval_cases()
    if config.DRY_RUN:
        typer.echo(
            "[DRY RUN] Opik creds not set. Would create dataset "
            f"'{config.DATASET_NAME}' and test suite '{config.SUITE_NAME}' with:"
        )
        for case in cases:
            typer.echo(f"  query: {case['query']}")
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
    """Run Optimization Studio against the eval dataset to improve the summariser prompt."""
    cases = load_eval_cases()
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
    cases = load_eval_cases()
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
    """Run the full demo loop: ingest -> eval -> optimize -> promote."""
    ingest()
    eval_cmd()
    optimize()
    promote()


if __name__ == "__main__":
    app()
