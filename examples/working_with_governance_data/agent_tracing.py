"""
Business Unit — Agent Tracing (Production)
==========================================
Demonstrates how to instrument an agent with:
  - @opik.track decorator
  - Governance tag for cross-team reporting
  - Governance metadata on every trace
  - Raw signal feedback scores (hallucination_rate, response_quality, cost_usd)

Online evaluation rules (Python metrics and LLM judges) are set up separately
in the Opik web app and fire automatically on every trace this script produces.

The main block runs the agent three times with different inputs to populate
the project with representative data.

Usage:
    python agent_tracing.py

Required env vars:
    OPIK_API_KEY
    OPIK_WORKSPACE
    OPIK_PROJECT_NAME   (optional, defaults to "governance-data-demo")
    OPIK_URL_OVERRIDE   (optional, for self-hosted deployments)

Docs:
    https://www.comet.com/docs/opik/tracing/log_traces
    https://www.comet.com/docs/opik/tracing/log_metadata
    https://www.comet.com/docs/opik/tracing/annotate_traces
"""

import os
import time

import opik
from opik import opik_context

PROJECT_NAME    = os.environ.get("OPIK_PROJECT_NAME", "governance-data-demo")

# Tag applied to every trace. The oversight/reporting team filters on this tag
# to identify which traces belong to the governance programme.
# Replace with whatever tag your organisation uses.
GOVERNANCE_TAG  = "governance"


# ---------------------------------------------------------------------------
# Agent implementation
# ---------------------------------------------------------------------------

@opik.track(name="retrieve_context", type="tool")
def retrieve_context(query: str) -> list[str]:
    opik_context.update_current_span(metadata={"retriever": "vector-index-v3", "top_k": 5})
    time.sleep(0.01)
    return [
        "Applicant has an existing credit facility of $15,000.",
        "No missed payments in the last 24 months.",
        "Current utilisation: 42%.",
    ]


@opik.track(name="call_llm", type="llm")
def call_llm(query: str, context_docs: list[str], model: str) -> str:
    opik_context.update_current_span(
        metadata={"model": model, "prompt_tokens": 512, "completion_tokens": 128}
    )
    time.sleep(0.02)
    return (
        "Based on the provided context, the risk assessment for this "
        "application is LOW. Recommended approval."
    )


@opik.track(
    name="loan_approval_assessment",
    tags=[GOVERNANCE_TAG, "use-case:loan-approval", "env:prod"],
    project_name=PROJECT_NAME,
)
def run_agent(
    query: str,
    request_id: str,
    business_unit: str,
    risk_tier: str,
    hallucination_rate: float,
    response_quality: float,
    cost_usd: float,
) -> dict:
    """
    Agent entrypoint. The decorator creates the trace; governance metadata
    and raw signal scores are attached inside the function body.
    """
    model = "gpt-4o"

    opik.update_current_trace(
        metadata={
            # Governance fields — the oversight team filters and slices on all of these.
            # Adapt field names and values to match your organisation's schema.
            "env":                 "prod",
            "region":              "us-east",
            "use_case_id":         "loan-approval",
            "use_case_version":    "2.1.0",
            "team":                "risk-analytics",
            "business_unit":       business_unit,
            "model_name":          model,
            "model_version":       "2024-11-20",
            "risk_tier":           risk_tier,
            "data_classification": "confidential",
            "regulatory_scope":    "internal",
            # Call-level runtime fields
            "request_id":          request_id,
            "channel":             "api",
        }
    )

    context_docs = retrieve_context(query)
    answer       = call_llm(query, context_docs, model)
        
    return {"answer": answer, "sources": context_docs}


# ---------------------------------------------------------------------------
# Main — run the agent three times with varied inputs to populate the project
# ---------------------------------------------------------------------------

SAMPLE_RUNS = [
    {
        "query":              "Assess the risk for a $20,000 personal loan application.",
        "request_id":         "req-001",
        "business_unit":      "retail",
        "risk_tier":          "high",
        "hallucination_rate": 0.03,
        "response_quality":   0.91,
        "cost_usd":           0.0042,
    },
    {
        "query":              "Evaluate eligibility for a $500,000 business loan.",
        "request_id":         "req-002",
        "business_unit":      "commercial",
        "risk_tier":          "medium",
        "hallucination_rate": 0.07,
        "response_quality":   0.84,
        "cost_usd":           0.0061,
    },
    {
        "query":              "Review a credit limit increase request from $10,000 to $25,000.",
        "request_id":         "req-003",
        "business_unit":      "wealth",
        "risk_tier":          "low",
        "hallucination_rate": 0.01,
        "response_quality":   0.97,
        "cost_usd":           0.0038,
    },
]

if __name__ == "__main__":
    print(f"Project  : {PROJECT_NAME}")
    print(f"Tag      : {GOVERNANCE_TAG}\n")

    for i, run in enumerate(SAMPLE_RUNS, 1):
        print(f"Run {i}/3 — {run['request_id']} ({run['business_unit']}, risk_tier={run['risk_tier']})")
        result = run_agent(**run)
        print(f"  Answer : {result['answer'][:80]}...\n")

    opik.flush_tracker()
    print("Done. Traces are visible in the Opik UI under the project:")
    print(f"  https://www.comet.com/opik/{os.environ['OPIK_WORKSPACE']}/{PROJECT_NAME}/traces")
