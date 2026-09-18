import asyncio
from pathlib import Path

import typer

from . import config
from .report import render_report, render_runs_table

app = typer.Typer(
    add_completion=False,
    help="MCP-driven GPU capacity planning: Comet EM metrics -> LLM rightsizing -> Opik traces.",
)

MCP_TOOLS = (
    "list_projects, list_experiments, get_experiment_details, "
    "get_experiment_parameters, get_experiment_metric_data"
)


def _resolve(workspace: str | None, synthetic: bool) -> tuple[str, bool]:
    use_synthetic = synthetic or config.SYNTHETIC
    ws = workspace or (config.SYNTHETIC_WORKSPACE if use_synthetic else config.COMET_WORKSPACE)
    if not ws:
        typer.echo("Set COMET_WORKSPACE (or pass --workspace), or run with --synthetic.")
        raise typer.Exit(1)
    return ws, use_synthetic


@app.command()
def audit(
    workspace: str = typer.Option(None, help="Comet workspace (default: COMET_WORKSPACE)"),
    project: list[str] = typer.Option(None, "--project", "-p", help="Project(s); default: all"),
    max_runs: int = typer.Option(config.MAX_RUNS, help="Cap on experiments swept"),
    synthetic: bool = typer.Option(False, help="Force the bundled synthetic MCP server"),
    output: Path = typer.Option(None, help="Also write the Markdown report here"),
) -> None:
    """Sweep runs via the Comet MCP server, flag waste, and write an LLM rightsizing report."""
    ws, use_synthetic = _resolve(workspace, synthetic)
    from .audit import run_audit

    result = asyncio.run(
        run_audit(ws, project or None, max_runs, use_synthetic, config.LOW_UTIL_PCT, config.IDLE_UTIL_PCT)
    )
    report = render_report(
        result.summary,
        result.findings,
        result.recommendations_md,
        "synthetic" if use_synthetic else "live",
    )
    typer.echo(report)
    if config.DRY_RUN:
        typer.echo(
            f"\n[DRY RUN] Opik credentials not set - would call {config.GEN_MODEL} for the "
            f"recommendations section and log the audit trace to Opik project "
            f"'{config.OPIK_PROJECT_NAME}'."
        )
    if output:
        output.write_text(report)
        typer.echo(f"\nReport written to {output}")


@app.command("list-runs")
def list_runs(
    workspace: str = typer.Option(None, help="Comet workspace (default: COMET_WORKSPACE)"),
    project: list[str] = typer.Option(None, "--project", "-p", help="Project(s); default: all"),
    max_runs: int = typer.Option(config.MAX_RUNS, help="Cap on experiments swept"),
    synthetic: bool = typer.Option(False, help="Force the bundled synthetic MCP server"),
) -> None:
    """Collection only - the per-run metrics table, no LLM call."""
    ws, use_synthetic = _resolve(workspace, synthetic)
    from .collector import collect_runs
    from .mcp_client import comet_session

    async def _collect():
        async with comet_session(use_synthetic) as session:
            return await collect_runs(session, ws, project or None, max_runs)

    typer.echo(render_runs_table(asyncio.run(_collect())))


@app.command()
def report(
    project: str = typer.Option(..., "--project", "-p", help="Project holding the training runs"),
    experiment: list[str] = typer.Option(
        None, "--experiment", "-e", help="Experiment key(s) or name(s); default: all in the project"
    ),
    workspace: str = typer.Option(None, help="Comet workspace (default: COMET_WORKSPACE)"),
    synthetic: bool = typer.Option(False, help="Force the bundled synthetic MCP server"),
    output: Path = typer.Option(None, help="Also write the Markdown report here"),
) -> None:
    """Post-training report: model quality + capacity efficiency + review links, traced in Opik."""
    ws, use_synthetic = _resolve(workspace, synthetic)
    from .training_report import add_report_to_queue, build_report

    result = asyncio.run(build_report(ws, project, experiment or None, use_synthetic))
    typer.echo(result.markdown)
    if config.DRY_RUN:
        typer.echo(
            f"\n[DRY RUN] Opik credentials not set - would call {config.GEN_MODEL} for the "
            f"recommendations section, log the report trace to Opik project "
            f"'{config.OPIK_PROJECT_NAME}', and add it to the '{config.QUEUE_NAME}' queue."
        )
    elif result.trace_id:
        queue = add_report_to_queue(result.trace_id)
        if queue:
            typer.echo(f"\nTrace {result.trace_id} added to annotation queue '{queue}'.")
        else:
            typer.echo(f"\nAnnotation queue '{config.QUEUE_NAME}' not found - run setup-loop to create it.")
    if output:
        output.write_text(result.markdown)
        typer.echo(f"\nReport written to {output}")


@app.command("setup-loop")
def setup_loop() -> None:
    """Create the Opik feedback loop: prompt in the library, annotation queue, online judge rule."""
    if config.DRY_RUN:
        typer.echo("Opik credentials (OPIK_API_KEY + OPIK_WORKSPACE) are required for setup-loop.")
        raise typer.Exit(1)
    from .loop_setup import ensure_loop

    for line in ensure_loop():
        typer.echo(f"- {line}")


@app.command()
def curate(
    min_score: float = typer.Option(0.8, help="Minimum feedback score a trace needs"),
    dataset: str = typer.Option(config.GOLDEN_DATASET, help="Target Opik dataset"),
    max_items: int = typer.Option(50, help="Cap on traces considered"),
) -> None:
    """Copy recommendation traces rated >= min-score into the golden evaluation dataset."""
    if config.DRY_RUN:
        typer.echo("Opik credentials (OPIK_API_KEY + OPIK_WORKSPACE) are required for curate.")
        raise typer.Exit(1)
    from .curation import curate as run_curate

    sent = run_curate(min_score, dataset, max_items)
    typer.echo(
        f"{sent} report trace(s) with {config.JUDGE_SCORE_NAME} >= {min_score} sent to dataset "
        f"'{dataset}' (re-inserting an unchanged trace is a no-op - items deduplicate)."
    )


@app.command()
def evaluate(
    dataset: str = typer.Option(config.GOLDEN_DATASET, help="Opik dataset to evaluate against"),
    experiment_name: str = typer.Option(None, help="Experiment name (default: generated)"),
) -> None:
    """Offline evaluation of the current prompt + model against the golden dataset."""
    if config.DRY_RUN:
        typer.echo(
            "Opik credentials (OPIK_API_KEY + OPIK_WORKSPACE) are required for evaluate, "
            f"plus an LLM provider key matching {config.GEN_MODEL}."
        )
        raise typer.Exit(1)
    from .offline_eval import run_offline_eval

    name = run_offline_eval(dataset, experiment_name)
    typer.echo(f"Offline evaluation logged as Opik experiment '{name}'.")


@app.command()
def ask(
    question: str,
    workspace: str = typer.Option(None, help="Comet workspace (default: COMET_WORKSPACE)"),
    synthetic: bool = typer.Option(False, help="Force the bundled synthetic MCP server"),
    max_turns: int = typer.Option(8, help="Tool-use loop bound"),
) -> None:
    """Let the LLM drive the comet-mcp tools to answer a free-form capacity question."""
    ws, use_synthetic = _resolve(workspace, synthetic)
    if config.DRY_RUN:
        typer.echo(
            f"[DRY RUN] Opik/LLM credentials not set - would start a comet-mcp session and let "
            f"{config.GEN_MODEL} answer via tools: {MCP_TOOLS}."
        )
        return
    from .agent import ask as agent_ask
    from .mcp_client import comet_session

    async def _ask():
        async with comet_session(use_synthetic) as session:
            return await agent_ask(session, question, ws, max_turns=max_turns)

    typer.echo(asyncio.run(_ask()))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
