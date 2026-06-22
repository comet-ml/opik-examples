# Nesting out-of-process tool calls in Opik with OpenTelemetry

**Quick rule: if you can carry one HTTP header across the process boundary, use Option B. If you can't, use Option A.**

Both scripts produce the same corrected trace; they differ only in *how* the link is carried across the boundary where the tool runs out of process.

| Script | How it links the spans | Use when |
|---|---|---|
| `option_a_explicit_ids.py` | explicit Opik ids on the span | the out-of-process hop **can't** carry trace context back |
| `option_b_w3c_propagation.py` | standard W3C `traceparent` propagation | one header **can** be passed back across the hop |

## The problem

The backend is OpenTelemetry-instrumented. An LLM call decides to invoke a tool; the tool runs **out of process** (e.g. backend → UI → third-party service), and the result returns to the backend as a **separate request**. That second request has no live OTel context from the first, so its spans land as a disconnected root instead of nesting under the span that dispatched the tool:

```text
 Current behavior                          Desired behavior
 orchestrator_request                      orchestrator_request
   routing.invoke                            routing.invoke
     routing.generic_agent                     routing.generic_agent
       llm.request (LLM #1)                       llm.request (LLM #1)
         tool_dispatch                               tool_dispatch
 tool_execution   ← disconnected                      tool_execution        ← nested
   routing.invoke                                       routing.invoke
     routing.generic_agent                                routing.generic_agent
                                                            llm.request (LLM #2, final)
```

## Option A: link by id (`option_a_explicit_ids.py`)

Opik's OTLP ingest honors three span attributes that attach a span to an
**existing** trace/span *by id*, with **no live OTel context required**:

| Attribute | Meaning |
|---|---|
| `opik.trace_id` | id of the Opik trace to attach to |
| `opik.parent_span_id` | id of the parent span within that trace |
| `opik.span_id` | id for this span |

Approach:

1. In request 1, mint the ids and set them on every span.
2. Persist `{trace_id, dispatch_span_id}` keyed by the session/request id (already carried through the round-trip).
3. In request 2, set `opik.trace_id` to the persisted trace id and `opik.parent_span_id` to the persisted `tool_dispatch` span id on the `tool_execution` span. It nests there deterministically.

Only two id strings cross the network, so this works even when the out-of-process hop can't keep a trace open or carry context.

Two things to know:

- **Ids must be UUIDv7** (e.g. `uuid6.uuid7()`). Other id formats are ignored on ingest.
- **When `opik.trace_id` is set, parentage comes from `opik.parent_span_id` and the native OTel parent is ignored.** Set `opik.parent_span_id` on every non-root span (the example's `emit_span` helper handles this).

## Option B: propagate the context (`option_b_w3c_propagation.py`)

Standard OpenTelemetry. Build the tree with normal span nesting; at the dispatch point, serialize the current context into a carrier and send that one header across:

```python
inject(carrier)   # carrier == {"traceparent": "00-<trace>-<dispatch_span>-01"}
```

The external service runs the tool, hands `traceparent` back, and request 2 rebuilds the context and starts the tool span under it:

```python
ctx = extract(carrier)
with tracer.start_as_current_span("tool_execution", context=ctx):
    ...
```

Same trace id, correct parent span, and the tool span nests under `tool_dispatch`.

When the raw OpenTelemetry ids are left to drive trace assembly, Opik converts them into its own ids using timestamps, and that conversion is the likely cause of a second request tying to the wrong trace. Both options above avoid it: Option A by setting the ids explicitly, Option B by ensuring a single real trace id actually propagates. If the context can't be guaranteed to cross the hop, Option A is the safer choice.

## Running the examples

```bash
pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http uuid6

# Send to your Opik deployment:
export OPIK_OTEL_ENDPOINT="https://<opik-host>/api/v1/private/otel/v1/traces"
export OPIK_API_KEY="<api-key>"
export OPIK_WORKSPACE="<workspace>"
export OPIK_PROJECT_NAME="otel-distributed-tracing-demo"

python option_a_explicit_ids.py        # Option A
python option_b_w3c_propagation.py     # Option B
```

Without the env vars set, each script runs in dry-run mode: prints the spans and the reconstructed trace tree locally without sending anything.

## Attribute reference (OpenTelemetry → Opik)

| OTel span attribute | Becomes in Opik |
|---|---|
| `opik.trace_id` / `opik.parent_span_id` / `opik.span_id` | explicit trace/span link (UUIDv7) |
| `input*` / `output*` | input / output |
| `gen_ai.request.model` (or `gen_ai.response.model`) | model; also marks the span as an LLM span |
| `gen_ai.system` | provider |
| `gen_ai.usage.*` | token usage |
| `gen_ai.usage.cost` | cost |
| `gen_ai.tool.*` / `gen_ai.agent.*` | metadata |
| `opik.tags` | tags |
| `opik.metadata.*` | metadata |

Opik is open source, so the exact attribute handling can be reviewed in the `comet-ml/opik` backend.

There's no attribute that sets span type `tool`; tool spans come through as type `general`.
