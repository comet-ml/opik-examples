"""
Opik + OpenTelemetry: stitching out-of-process tool calls with explicit Opik ids.

Option A of two approaches — see README.md for the decision guide.
Use this when the out-of-process hop CANNOT carry a trace header back.

────────────────────────────────────────────────────────────────────────────
THE PROBLEM
────────────────────────────────────────────────────────────────────────────
The backend is OTel-instrumented. It calls an LLM that decides to invoke a
tool. The tool runs OUT OF PROCESS (e.g. backend → UI → third-party service),
and the result arrives back at the backend as a SEPARATE request. That second
request has no live OTel context from the first, so its spans land as a
DISCONNECTED root instead of nesting under the span that dispatched the tool:

    orchestrator_request                 orchestrator_request
      routing.invoke                       routing.invoke
        routing.generic_agent               routing.generic_agent
          llm.request (LLM #1)                llm.request (LLM #1)
            tool_dispatch         --->          tool_dispatch
    tool_execution  <-- DISCONNECTED              tool_execution  <-- nested ✔
      routing.invoke                                routing.invoke
        routing.generic_agent                         routing.generic_agent
                                                         llm.request (LLM #2, final)

────────────────────────────────────────────────────────────────────────────
THE FIX
────────────────────────────────────────────────────────────────────────────
Opik's OTLP ingest honors three span attributes that pin a span to an EXISTING
Opik trace/span *by id* (no live OTel context required):

    opik.trace_id        UUIDv7 of the Opik trace to attach to
    opik.parent_span_id  UUIDv7 of the parent span within that trace
    opik.span_id         UUIDv7 id for this span

Mint these ids up front, persist {trace_id, dispatch_span_id} keyed by the
session/request id, and set them on the tool spans in the second request.
The spans then nest deterministically, across the process boundary, with
nothing extra carried over the network (the session id already round-trips).

# WHY the helper sets opik.parent_span_id on EVERY non-root span:
# When opik.trace_id is present, Opik takes parentage from opik.parent_span_id
# and IGNORES the native OTel parent. Omitting it on any span would make that
# span a disconnected root inside the Opik trace.

────────────────────────────────────────────────────────────────────────────
RUN
────────────────────────────────────────────────────────────────────────────
  pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http uuid6

  # Send to Opik:
  export OPIK_OTEL_ENDPOINT="https://<opik-host>/api/v1/private/otel/v1/traces"
  export OPIK_API_KEY="<api-key>"
  export OPIK_WORKSPACE="<workspace>"
  export OPIK_PROJECT_NAME="otel-distributed-tracing-demo"
  python option_a_explicit_ids.py

  # No creds? Runs in DRY-RUN: prints the reconstructed trace tree locally.
"""

import json
import os
import time

import uuid6  # same UUIDv7 generator Opik's own SDK uses (opik.id_helpers)
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# ── OTel -> Opik wiring ──────────────────────────────────────────────────────
ENDPOINT = os.environ.get(
    "OPIK_OTEL_ENDPOINT",
    "https://www.comet.com/opik/api/v1/private/otel/v1/traces",  # Opik Cloud default
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
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("agent.otel.demo")


def new_id() -> str:
    """UUIDv7: the required form for the opik.* linking attributes."""
    return str(uuid6.uuid7())


# Records every emitted span so we can print the reconstructed tree at the end.
_EMITTED: list[dict] = []


def emit_span(
    name: str,
    *,
    trace_id: str,
    span_id: str,
    parent_span_id: str | None,
    attributes: dict | None = None,
    duration_s: float = 0.05,
) -> None:
    """
    Emit a single OTel span pinned to an explicit Opik trace/parent.

    Because parentage is carried by the opik.* ids (not OTel context), spans can
    be emitted in ANY order and from ANY process — exactly what lets the second
    backend request attach under a span created by the first.
    """
    attrs: dict[str, object] = {
        "opik.trace_id": trace_id,
        "opik.span_id": span_id,
    }
    if parent_span_id:
        attrs["opik.parent_span_id"] = parent_span_id
    # OTel attribute values must be primitives; JSON-encode structured payloads.
    for k, v in (attributes or {}).items():
        attrs[k] = v if isinstance(v, (str, bool, int, float)) else json.dumps(v)

    span = tracer.start_span(name)
    span.set_attributes(attrs)
    time.sleep(duration_s)  # give the span a realistic, non-zero duration
    span.end()

    _EMITTED.append({"name": name, "span_id": span_id, "parent": parent_span_id})


def llm_attrs(model: str, prompt, completion, usage: dict) -> dict:
    """
    GenAI attributes Opik maps to an LLM span (type=llm) with model + token usage.
    `usage` keys map under gen_ai.usage.* (input_tokens, output_tokens, etc.).
    """
    attrs = {
        "gen_ai.system": "openai",  # -> provider
        "gen_ai.request.model": model,  # -> model, forces span type = llm
        "input": prompt,  # -> input
        "output": completion,  # -> output
    }
    for token_type, count in usage.items():
        attrs[f"gen_ai.usage.{token_type}"] = count
    return attrs


# ── Simulated cross-request state ────────────────────────────────────────────
# Stands in for whatever is persisted between requests (Redis, DB, or echoed
# through the UI round-trip). Only TWO strings need to travel: the Opik
# trace_id and the id of the span the tool result should nest under.
SESSION_STORE: dict[str, dict] = {}


def backend_request_1(session_id: str, user_prompt: str) -> dict:
    """
    First backend hit: orchestrator runs LLM #1, which decides to call a tool,
    then dispatches it to the UI/external service (out of process).
    """
    trace_id = new_id()
    s_orchestrator = new_id()  # root span (closes last, in finalize())
    s_routing = new_id()
    s_agent = new_id()
    s_llm1 = new_id()
    s_dispatch = new_id()  # tool_dispatch: tool result must nest UNDER this

    emit_span(
        "routing.invoke", trace_id=trace_id, span_id=s_routing, parent_span_id=s_orchestrator, duration_s=0.1
    )
    emit_span(
        "routing.generic_agent", trace_id=trace_id, span_id=s_agent, parent_span_id=s_routing, duration_s=0.1
    )
    emit_span(
        "llm.request",
        trace_id=trace_id,
        span_id=s_llm1,
        parent_span_id=s_agent,
        duration_s=0.3,
        attributes=llm_attrs(
            model="gpt-4o",
            prompt=[{"role": "user", "content": user_prompt}],
            completion=[
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"id": "call_1", "name": "web_search", "arguments": {"query": user_prompt}}
                    ],
                }
            ],
            usage={"input_tokens": 412, "output_tokens": 37},
        ),
    )
    emit_span(
        "tool_dispatch",
        trace_id=trace_id,
        span_id=s_dispatch,
        parent_span_id=s_llm1,
        duration_s=0.02,
        attributes={
            "gen_ai.tool.name": "web_search",
            "gen_ai.tool.call.id": "call_1",
            "input": {"query": user_prompt},
        },
    )

    # Persist the two ids the second request needs to stitch the trace correctly.
    SESSION_STORE[session_id] = {
        "trace_id": trace_id,
        "orchestrator_span_id": s_orchestrator,
        "dispatch_span_id": s_dispatch,
        "user_prompt": user_prompt,
    }
    # Returned to the UI so it can run the tool, then call back into request 2.
    return {"tool": "web_search", "args": {"query": user_prompt}, "session_id": session_id}


def backend_request_2(session_id: str, tool_result: dict) -> str:
    """
    Second backend hit: the UI has run the tool out of process and is returning
    the result. Rebuild parentage from the persisted ids so the tool + final-LLM
    spans nest under the dispatch span from request 1.
    """
    ctx = SESSION_STORE[session_id]
    trace_id = ctx["trace_id"]

    s_tool = new_id()
    s_routing2 = new_id()
    s_agent2 = new_id()
    s_llm2 = new_id()

    # THE KEY LINE: parent is the dispatch span id from request 1 — no longer a
    # disconnected root.
    emit_span(
        "tool_execution",
        trace_id=trace_id,
        span_id=s_tool,
        parent_span_id=ctx["dispatch_span_id"],
        duration_s=0.2,
        attributes={
            "gen_ai.tool.name": "web_search",
            "gen_ai.tool.call.id": "call_1",
            "input": ctx["user_prompt"],
            "output": tool_result,
        },
    )
    emit_span("routing.invoke", trace_id=trace_id, span_id=s_routing2, parent_span_id=s_tool, duration_s=0.1)
    emit_span(
        "routing.generic_agent",
        trace_id=trace_id,
        span_id=s_agent2,
        parent_span_id=s_routing2,
        duration_s=0.1,
    )

    final_answer = "The capital of France is Paris."
    emit_span(
        "llm.request",
        trace_id=trace_id,
        span_id=s_llm2,
        parent_span_id=s_agent2,
        duration_s=0.3,
        attributes=llm_attrs(
            model="gpt-4o",
            prompt=[{"role": "tool", "content": tool_result}],
            completion=[{"role": "assistant", "content": final_answer}],
            usage={"input_tokens": 690, "output_tokens": 122},
        ),
    )

    ctx["final_answer"] = final_answer
    return final_answer


def finalize(session_id: str) -> None:
    """
    Orchestrator root span closes LAST, spanning the full round-trip.
    thread_id groups the trace into a conversation thread in Opik.
    """
    ctx = SESSION_STORE[session_id]
    emit_span(
        "orchestrator_request",
        trace_id=ctx["trace_id"],
        span_id=ctx["orchestrator_span_id"],
        parent_span_id=None,
        duration_s=0.05,
        attributes={
            "thread_id": session_id,  # -> Opik thread grouping
            "input": ctx["user_prompt"],  # -> trace input
            "output": ctx["final_answer"],  # -> trace output
            "opik.tags": ["tool-call", "distributed", "demo"],
        },
    )


def print_tree() -> None:
    by_parent: dict[str | None, list[dict]] = {}
    for s in _EMITTED:
        by_parent.setdefault(s["parent"], []).append(s)

    def walk(parent: str | None, depth: int) -> None:
        for s in by_parent.get(parent, []):
            print("    " * depth + "└─ " + s["name"])
            walk(s["span_id"], depth + 1)

    print("\nReconstructed Opik trace tree:")
    walk(None, 0)


if __name__ == "__main__":
    session = new_id()  # session / thread id
    prompt = "What is the capital of France?"

    # 1) Backend calls LLM #1, which dispatches a tool out of process.
    call = backend_request_1(session, prompt)

    # 2) ── PROCESS BOUNDARY ──  UI/external service runs the tool...
    search_result = {"status": "ok", "results": ["Paris is the capital of France."]}

    # 3) ...and calls back with the result. Stitch it into the SAME trace.
    backend_request_2(session, search_result)

    # 4) Orchestrator closes last with the final answer + thread_id.
    finalize(session)

    provider.force_flush()
    provider.shutdown()
    print_tree()
    print(f"\nDRY_RUN={DRY_RUN}  trace_id={SESSION_STORE[session]['trace_id']}  thread_id={session}")
    if DRY_RUN:
        print("Set OPIK_API_KEY / OPIK_WORKSPACE / OPIK_OTEL_ENDPOINT to send to Opik.")
