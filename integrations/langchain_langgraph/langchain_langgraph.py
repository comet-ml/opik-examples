#!/usr/bin/env python3
"""Trace LangChain runnables inside a LangGraph workflow with Opik."""

import argparse
import os
import sys
from typing import TypedDict

OPIK_API_KEY = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE")
OPIK_PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME", "langchain-langgraph")
OPIK_URL = os.environ.get("OPIK_URL_OVERRIDE", "https://www.comet.com/opik/api")

DEFAULT_QUESTION = "Hello, I need help understanding my latest invoice."
DRY_RUN = not (OPIK_API_KEY and OPIK_WORKSPACE)


class SupportState(TypedDict, total=False):
    question: str
    classification: str
    response: str


def classify_question(question: str) -> str:
    text = question.casefold()
    if any(term in text for term in ("bill", "billing", "invoice", "payment", "price", "refund")):
        return "billing"
    if any(term in text for term in ("bug", "crash", "error", "login", "broken", "timeout")):
        return "technical"
    if any(term in text for term in ("hello", "hi ", "hey", "good morning", "good afternoon")):
        return "greeting"
    return "general"


def route_by_classification(state: SupportState) -> str:
    classification = state.get("classification", "general")
    return {
        "greeting": "handle_greeting",
        "billing": "handle_billing",
        "technical": "handle_technical",
    }.get(classification, "handle_general")


def build_support_response(state: SupportState) -> dict[str, str]:
    question = state.get("question", "")
    classification = state.get("classification", "general")
    responses = {
        "greeting": "Greeting: welcome the customer and ask how you can help.",
        "billing": "Billing: route the customer to invoice, payment, or refund support.",
        "technical": "Technical: collect reproduction details and route to product support.",
        "general": "General: acknowledge the request and ask one clarifying question.",
    }
    return {
        "response": f"{responses.get(classification, responses['general'])} Original question: {question}",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--question", default=DEFAULT_QUESTION, help="Support question to route through the graph."
    )
    parser.add_argument(
        "--thread-id", default="langchain-langgraph-demo", help="Thread ID attached to the trace."
    )
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen; do not touch Opik.")
    return parser


def run_dry(question: str, thread_id: str) -> SupportState:
    classification = classify_question(question)
    result: SupportState = {
        "question": question,
        "classification": classification,
        **build_support_response({"question": question, "classification": classification}),
    }
    print("[DRY RUN] would trace a LangGraph support router to Opik")
    print(f"  project: {OPIK_PROJECT_NAME}")
    print(f"  thread_id: {thread_id}")
    print(f"  opik_url: {OPIK_URL}")
    print(f"  classification: {result['classification']}")
    print(f"  response: {result['response']}")
    return result


def build_graph():
    from langchain_core.runnables import RunnableLambda
    from langgraph.graph import END, START, StateGraph

    classify_chain = RunnableLambda(classify_question).with_config({"run_name": "classify_question"})
    response_chain = RunnableLambda(build_support_response).with_config(
        {"run_name": "build_support_response"}
    )

    def classify_node(state: SupportState) -> dict[str, str]:
        return {"classification": classify_chain.invoke(state["question"])}

    def response_node(state: SupportState) -> dict[str, str]:
        return response_chain.invoke(state)

    workflow = StateGraph(SupportState)
    workflow.add_node("classify", classify_node)
    workflow.add_node("handle_greeting", response_node)
    workflow.add_node("handle_billing", response_node)
    workflow.add_node("handle_technical", response_node)
    workflow.add_node("handle_general", response_node)
    workflow.add_edge(START, "classify")
    workflow.add_conditional_edges(
        "classify",
        route_by_classification,
        {
            "handle_greeting": "handle_greeting",
            "handle_billing": "handle_billing",
            "handle_technical": "handle_technical",
            "handle_general": "handle_general",
        },
    )
    workflow.add_edge("handle_greeting", END)
    workflow.add_edge("handle_billing", END)
    workflow.add_edge("handle_technical", END)
    workflow.add_edge("handle_general", END)
    return workflow.compile()


def run_live(question: str, thread_id: str) -> SupportState:
    from opik.integrations.langchain import OpikTracer, track_langgraph

    opik_tracer = OpikTracer(
        project_name=OPIK_PROJECT_NAME,
        tags=["langchain", "langgraph", "support-router"],
        metadata={"example": "langchain_langgraph"},
    )
    app = track_langgraph(build_graph(), opik_tracer)
    result = app.invoke(
        {"question": question},
        config={"configurable": {"thread_id": thread_id}},
    )
    opik_tracer.flush()
    return result


def main() -> int:
    args = build_parser().parse_args()
    dry_run = DRY_RUN or args.dry_run

    if dry_run:
        if not args.dry_run:
            print("OPIK_API_KEY / OPIK_WORKSPACE not set - running in DRY_RUN.", file=sys.stderr)
        run_dry(args.question, args.thread_id)
        return 0

    result = run_live(args.question, args.thread_id)
    print(result["response"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
