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
            f"\n[DRY RUN] Opik credentials not set — would call {config.GEN_MODEL} for the "
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
    """Collection only — the per-run metrics table, no LLM call."""
    ws, use_synthetic = _resolve(workspace, synthetic)
    from .collector import collect_runs
    from .mcp_client import comet_session

    async def _collect():
        async with comet_session(use_synthetic) as session:
            return await collect_runs(session, ws, project or None, max_runs)

    typer.echo(render_runs_table(asyncio.run(_collect())))


@app.command()
def ask(
    question: str,
    synthetic: bool = typer.Option(False, help="Force the bundled synthetic MCP server"),
    max_turns: int = typer.Option(8, help="Tool-use loop bound"),
) -> None:
    """Let the LLM drive the comet-mcp tools to answer a free-form capacity question."""
    _, use_synthetic = _resolve(None, synthetic)
    if config.DRY_RUN:
        typer.echo(
            f"[DRY RUN] Opik/LLM credentials not set — would start a comet-mcp session and let "
            f"{config.GEN_MODEL} answer via tools: {MCP_TOOLS}."
        )
        return
    from .agent import ask as agent_ask
    from .mcp_client import comet_session

    async def _ask():
        async with comet_session(use_synthetic) as session:
            return await agent_ask(session, question, max_turns=max_turns)

    typer.echo(asyncio.run(_ask()))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
