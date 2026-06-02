"""
Automating Annotation Queues in Opik
=====================================
This script demonstrates two methods for automatically populating annotation queues:

Method 1 - Batch (run once daily as a scheduled job):
    Fetch all traces, apply filters, and assign them to queues in round-robin order.

Method 2 - Real-time (inline with trace logging):
    Add traces to annotation queues as they are created during inference using
    opik.opik_context.get_current_trace_data() to access the live trace ID.
"""

import random
import opik
from opik import track, opik_context

PROJECT_NAME = "test-annotate"

SAMPLE_INPUTS = [
    "What is the capital of France?",
    "Summarize the French Revolution in one sentence.",
    "Who wrote Les Misérables?",
    "What language is spoken in Quebec?",
    "Explain the Eiffel Tower's construction year.",
]

# ---------------------------------------------------------------------------
# Method 1: Batch assignment (run as a daily scheduled job)
# ---------------------------------------------------------------------------

def batch_assign_traces_to_queues():
    """
    Fetch traces from Opik, filter them, and distribute across annotation
    queues in round-robin order. Designed to run once a day as a cron job
    or scheduled task.
    """
    client = opik.Opik()

    # --- Get or create annotation queues ---
    queue_configs = [
        {"name": "Annotation Queue - Team A", "instructions": "Review for accuracy and tone."},
        {"name": "Annotation Queue - Team B", "instructions": "Focus on factual correctness."},
        {"name": "Annotation Queue - Team C", "instructions": "Check for harmful content."},
    ]

    queues = []
    existing_queues = {q.name: q for q in client.get_traces_annotation_queues(project_name=PROJECT_NAME)}

    for config in queue_configs:
        if config["name"] in existing_queues:
            queues.append(existing_queues[config["name"]])
        else:
            queue = client.create_traces_annotation_queue(
                name=config["name"],
                instructions=config["instructions"],
                feedback_definition_names=["relevance", "accuracy"],
            )
            queues.append(queue)
            print(f"Created queue: {queue.name}")

    # --- Fetch and filter traces ---
    # Example: pull traces with a low user satisfaction score for human review
    traces = client.search_traces(
        project_name=PROJECT_NAME,
        # filter_string="feedback_scores.user_satisfaction < 0.6",
    )

    if not traces:
        print("No traces matched the filter criteria.")
        return

    # Shuffle so assignment is not biased toward older traces
    random.shuffle(traces)

    # --- Round-robin distribution across queues ---
    for i, trace in enumerate(traces):
        target_queue = queues[i % len(queues)]
        target_queue.add_traces([trace])

    print(f"Assigned {len(traces)} traces across {len(queues)} queues.")


# ---------------------------------------------------------------------------
# Method 2: Real-time assignment (inline with trace creation)
# ---------------------------------------------------------------------------

def get_or_create_queue(client: opik.Opik, queue_name: str):
    """Return an existing queue by name, or create it if it doesn't exist."""
    existing = {q.name: q for q in client.get_traces_annotation_queues(project_name=PROJECT_NAME)}
    if queue_name in existing:
        return existing[queue_name]
    return client.create_traces_annotation_queue(
        name=queue_name,
        instructions="Review this trace for quality.",
        feedback_definition_names=["relevance", "accuracy"],
    )


@track()
def simulated_llm_call(user_input: str) -> str:
    """Simulated LLM call. Replace with your actual model invocation."""
    return f"Echo: {user_input}"


def seed_traces():
    """
    Log a small set of traces so the project exists in Opik before any
    annotation queue logic runs. Call this once before Method 1 or 2.
    """
    print("Seeding traces...")
    for user_input in SAMPLE_INPUTS:
        simulated_llm_call(user_input)
    opik.flush_tracker()
    print(f"Seeded {len(SAMPLE_INPUTS)} traces into project '{PROJECT_NAME}'.")


@track(project_name=PROJECT_NAME)
def my_llm_call(user_input: str, annotation_queue_name: str) -> str:
    """
    Top-level tracked function. Calls the LLM, then uses opik_context to grab
    the current trace ID and enqueue it without waiting for the trace to flush.
    """
    response = simulated_llm_call(user_input)

    trace_data = opik_context.get_current_trace_data()

    if trace_data is not None:
        client = opik.Opik()
        queue = get_or_create_queue(client, annotation_queue_name)

        trace = client.get_trace_content(trace_data.id)
        queue.add_traces([trace])
        print(f"Added trace {trace_data.id} to queue '{queue.name}'")

    return response


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    
    option = 1 # Change to 1 for batch assignment, 2 for real-time assignment

    if option == 1:
        seed_traces()

        print("=== Method 1: Batch assignment ===")
        batch_assign_traces_to_queues()

    else:
        print("\n=== Method 2: Real-time assignment ===")
        inputs = [
            "What is the capital of France?",
            "Summarize the French Revolution in one sentence.",
            "Who wrote Les Misérables?",
        ]
        for user_input in inputs:
            result = my_llm_call(
                user_input= user_input,
                annotation_queue_name="Real-time Review Queue",
            )
            print(f"LLM response: {result}")
