"""
Opik + OpenTelemetry: stitching out-of-process tool calls via W3C traceparent.

Option B of two approaches — see README.md for the decision guide.
Use this when one HTTP header CAN be carried across the process boundary and back.

────────────────────────────────────────────────────────────────────────────
HOW IT WORKS
────────────────────────────────────────────────────────────────────────────
Request 1 builds the span tree with normal OTel nesting. At the dispatch point
(`tool_dispatch`) we serialize the current span context into a carrier:

    inject(carrier)   # carrier == {"traceparent": "00-<trace>-<dispatch_span>-01"}

That one string crosses the process boundary. The external service runs the
tool and hands `traceparent` back. Request 2 rebuilds the context and starts
the tool span under it:

    ctx = extract(carrier)
    with tracer.start_as_current_span("tool_execution", context=ctx):
        ...

Result: same trace id + correct parent span id → Opik nests `tool_execution`
under `tool_dispatch`, no longer a disconnected root.

NOTE vs option_a_explicit_ids.py: here Opik derives its internal ids from the
raw OTel ids (timestamp-based conversion). That conversion is the likely cause
of a second request auto-tying to the wrong trace. It only behaves correctly
when the context genuinely propagates (single trace id, real parent span id),
which is exactly what this file demonstrates. If propagation can't be
guaranteed, prefer option_a_explicit_ids.py.

────────────────────────────────────────────────────────────────────────────
RUN
────────────────────────────────────────────────────────────────────────────
  pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http

  export OPIK_OTEL_ENDPOINT="https://<opik-host>/api/v1/private/otel/v1/traces"
  export OPIK_API_KEY="<api-key>"
  export OPIK_WORKSPACE="<workspace>"
  export OPIK_PROJECT_NAME="otel-distributed-tracing-demo"
  python option_b_w3c_propagation.py

  # No creds → DRY-RUN: prints the carrier value and the real OTel span tree.
"""

import json
import os
import time

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

# ── OTel -> Opik wiring ──────────────────────────────────────────────────────
ENDPOINT = os.environ.get(
    "OPIK_OTEL_ENDPOINT",
    "https://www.comet.com/opik/api/v1/private/otel/v1/traces",
)
DRY_RUN = not (os.environ.get("OPIK_API_KEY") and os.environ.get("OPIK_WORKSPACE"))

provider = TracerProvider()
if DRY_RUN:
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
else:
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=ENDPOINT,
                headers={
                    "Authorization": os.environ["OPIK_API_KEY"],
                    "projectName": os.environ.get("OPIK_PROJECT_NAME", "otel-distributed-tracing-demo"),
                    "Comet-Workspace": os.environ["OPIK_WORKSPACE"],
                },
            )
        )
    )

# Capture finished spans in memory so we can print the REAL OTel hierarchy as proof.
_MEMORY = InMemorySpanExporter()
provider.add_span_processor(SimpleSpanProcessor(_MEMORY))

trace.set_tracer_provider(provider)
tracer = trace.get_tracer("agent.otel.w3c.demo")


def set_attrs(span, attributes: dict) -> None:
    """OTel attribute values must be primitives; JSON-encode structured payloads."""
    span.set_attributes(
        {k: (v if isinstance(v, (str, bool, int, float)) else json.dumps(v))
         for k, v in attributes.items()}
    )


def llm_attrs(model: str, prompt, completion, usage: dict) -> dict:
    """GenAI attributes Opik maps to an LLM span (type=llm) with model + token usage."""
    attrs = {
        "gen_ai.system": "openai",
        "gen_ai.request.model": model,
        "input": prompt,
        "output": completion,
    }
    for token_type, count in usage.items():
        attrs[f"gen_ai.usage.{token_type}"] = count
    return attrs


# ── Simulated cross-request state ────────────────────────────────────────────
# Stands in for whatever is persisted between requests (Redis, DB, or echoed
# through the UI round-trip). With W3C propagation, the only extra thing that
# must travel is the `traceparent` string.
SESSION_STORE: dict[str, dict] = {}


def backend_request_1(session_id: str, user_prompt: str) -> dict:
    """First backend hit: orchestrator runs LLM #1, dispatches the tool, and
    injects the dispatch span's context into a carrier to hand to the UI."""
    # Orchestrator is the long-lived root span. Keep it open across the
    # round-trip; close it in finalize() with the final output.
    orchestrator = tracer.start_span("orchestrator_request")
    set_attrs(orchestrator, {"thread_id": session_id, "input": {"role": "user", "content": user_prompt}})

    carrier: dict[str, str] = {}
    with trace.use_span(orchestrator, end_on_exit=False):
        with tracer.start_as_current_span("routing.invoke"):
            time.sleep(0.05)
            with tracer.start_as_current_span("routing.generic_agent"):
                time.sleep(0.05)
                with tracer.start_as_current_span("llm.request") as llm1:
                    set_attrs(llm1, llm_attrs(
                        model="gpt-4o",
                        prompt=[{"role": "user", "content": user_prompt}],
                        completion=[{"role": "assistant", "tool_calls": [
                            {"id": "call_1", "name": "web_search", "arguments": {"query": user_prompt}}]}],
                        usage={"input_tokens": 412, "output_tokens": 37},
                    ))
                    time.sleep(0.2)
                    # Inject WHILE tool_dispatch is the current span so the carrier
                    # encodes it as the parent for the tool execution in request 2.
                    with tracer.start_as_current_span("tool_dispatch") as dispatch:
                        set_attrs(dispatch, {
                            "gen_ai.tool.name": "web_search",
                            "gen_ai.tool.call.id": "call_1",
                            "input": {"query": user_prompt},
                        })
                        inject(carrier)  # -> carrier["traceparent"] = 00-<trace>-<dispatch span>-01

    SESSION_STORE[session_id] = {"orchestrator": orchestrator, "carrier": carrier,
                                 "user_prompt": user_prompt}
    return {"tool": "web_search", "args": {"query": user_prompt},
            "session_id": session_id, "traceparent": carrier.get("traceparent")}


def backend_request_2(session_id: str, tool_result: dict) -> str:
    """Second backend hit: extract the propagated context and start the tool +
    final-LLM spans under it."""
    ctx_data = SESSION_STORE[session_id]
    parent_ctx = extract(ctx_data["carrier"])  # rebuilds the dispatch span context

    # THE KEY LINE: context=parent_ctx -> tool_execution becomes a child of
    # tool_dispatch, sharing the same trace id.
    with tracer.start_as_current_span("tool_execution", context=parent_ctx) as tool:
        set_attrs(tool, {
            "gen_ai.tool.name": "web_search",
            "gen_ai.tool.call.id": "call_1",
            "input": ctx_data["user_prompt"],
            "output": tool_result,
        })
        time.sleep(0.1)
        with tracer.start_as_current_span("routing.invoke"):
            time.sleep(0.05)
            with tracer.start_as_current_span("routing.generic_agent"):
                time.sleep(0.05)
                final_answer = "The capital of France is Paris."
                with tracer.start_as_current_span("llm.request") as llm2:
                    set_attrs(llm2, llm_attrs(
                        model="gpt-4o",
                        prompt=[{"role": "tool", "content": tool_result}],
                        completion=[{"role": "assistant", "content": final_answer}],
                        usage={"input_tokens": 690, "output_tokens": 122},
                    ))
                    time.sleep(0.2)

    ctx_data["final_answer"] = final_answer
    return final_answer


def finalize(session_id: str) -> None:
    """Orchestrator root closes last; its output becomes the trace-level output."""
    ctx = SESSION_STORE[session_id]
    orch = ctx["orchestrator"]
    set_attrs(orch, {"output": {"role": "assistant", "content": ctx["final_answer"]}})
    orch.end()


def print_tree() -> None:
    """Reconstruct the hierarchy from the REAL OTel span/parent ids (proof it nested)."""
    spans = _MEMORY.get_finished_spans()
    nodes = {s.context.span_id: (s.name, s.parent.span_id if s.parent else None) for s in spans}
    children: dict = {}
    for sid, (name, pid) in nodes.items():
        children.setdefault(pid if pid in nodes else None, []).append((sid, name))

    def walk(parent, depth):
        for sid, name in children.get(parent, []):
            print("    " * depth + "└─ " + name)
            walk(sid, depth + 1)

    print("\nReconstructed OTel span tree (from real trace/parent ids):")
    walk(None, 0)
    trace_ids = {s.context.trace_id for s in spans}
    print(f"\nDistinct OTel trace ids across all {len(spans)} spans: {len(trace_ids)} (want 1)")


if __name__ == "__main__":
    session = "demo-session-0001"  # session / thread id
    prompt = "What is the capital of France?"

    call = backend_request_1(session, prompt)
    print(f"Carrier crossing the boundary: {{'traceparent': '{call['traceparent']}'}}")

    # ── PROCESS BOUNDARY ──  External service runs the tool, returns traceparent.
    search_result = {"status": "ok", "results": ["Paris is the capital of France."]}
    backend_request_2(session, search_result)

    finalize(session)

    provider.force_flush()
    print_tree()
    print(f"\nDRY_RUN={DRY_RUN}  thread_id={session}")
    if DRY_RUN:
        print("Set OPIK_API_KEY / OPIK_WORKSPACE / OPIK_OTEL_ENDPOINT to send to Opik.")
    provider.shutdown()
