#!/usr/bin/env python3
"""Trace a Pydantic AI agent run to Opik."""

import argparse
import os
import sys

OPIK_API_KEY = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE")
OPIK_PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME", "pydantic-ai")
OPIK_OTLP_ENDPOINT = os.environ.get(
    "OPIK_OTLP_ENDPOINT",
    "https://www.comet.com/opik/api/v1/private/otel",
)

DEFAULT_MODEL = os.environ.get("PYDANTIC_AI_MODEL", "openai:gpt-4o-mini")
DEFAULT_QUESTION = "Where does the phrase hello world come from?"

PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "google-gla": "GEMINI_API_KEY",
    "google-vertex": "GOOGLE_APPLICATION_CREDENTIALS",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--question", default=DEFAULT_QUESTION, help="Question to send to the Pydantic AI agent."
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help="Pydantic AI model name, such as openai:gpt-4o-mini."
    )
    parser.add_argument(
        "--thread-id", default="pydantic-ai-demo", help="Thread ID attached to the Opik trace."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print what would happen; do not call an LLM or Opik."
    )
    return parser


def provider_key_env(model: str) -> str | None:
    provider = model.split(":", maxsplit=1)[0]
    return PROVIDER_KEY_ENV.get(provider)


def missing_live_inputs(model: str) -> list[str]:
    missing = []
    if not OPIK_API_KEY:
        missing.append("OPIK_API_KEY")
    if not OPIK_WORKSPACE:
        missing.append("OPIK_WORKSPACE")

    provider_env = provider_key_env(model)
    if provider_env and not os.environ.get(provider_env):
        missing.append(provider_env)

    return missing


def configure_opik_otlp() -> None:
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", OPIK_OTLP_ENDPOINT)
    os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
    os.environ.setdefault(
        "OTEL_EXPORTER_OTLP_HEADERS",
        f"Authorization={OPIK_API_KEY},Comet-Workspace={OPIK_WORKSPACE},projectName={OPIK_PROJECT_NAME}",
    )


def run_dry(question: str, model: str, thread_id: str, missing: list[str]) -> None:
    print("[DRY RUN] would trace a Pydantic AI agent call to Opik")
    print(f"  model: {model}")
    print(f"  project: {OPIK_PROJECT_NAME}")
    print(f"  thread_id: {thread_id}")
    print(f"  question: {question}")
    if missing:
        print(f"  missing for live run: {', '.join(missing)}")


def run_live(question: str, model: str, thread_id: str) -> str:
    import logfire
    import opik
    from opik.integrations.otel import OpikSpanProcessor
    from pydantic_ai import Agent

    configure_opik_otlp()
    logfire.configure(
        send_to_logfire=False,
        additional_span_processors=[OpikSpanProcessor()],
    )
    logfire.instrument_pydantic_ai()

    agent = Agent(
        model,
        instructions="Be concise and answer in one sentence.",
    )

    @opik.track(project_name=OPIK_PROJECT_NAME)
    def answer_question(user_question: str) -> str:
        with logfire.span("pydantic_ai_example", thread_id=thread_id):
            result = agent.run_sync(user_question)
            return result.output

    return answer_question(question)


def main() -> int:
    args = build_parser().parse_args()
    missing = missing_live_inputs(args.model)

    if args.dry_run or missing:
        if missing and not args.dry_run:
            print("Required credentials are not set - running in DRY_RUN.", file=sys.stderr)
        run_dry(args.question, args.model, args.thread_id, missing)
        return 0

    print(run_live(args.question, args.model, args.thread_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
