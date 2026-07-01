# Structuring Traces for Annotation Queues

Shows how to structure a RAG pipeline's traces so they are immediately useful in Opik [annotation queues](https://www.comet.com/docs/opik/evaluation/advanced/annotation_queues) — a clean answer in `output`, supporting context in `metadata`, and full technical detail preserved in child spans.

## What this does

A trace gives you four distinct places to put data: `input`, `output`, `metadata`, and child `spans`. A common default is to return the whole pipeline dict — answer, retrieved documents, the built prompt — as the trace `output`, which buries the answer a reviewer needs to score. This example shows how to distribute the data instead:

- `input` — the user's question
- `output` — the final answer only
- `metadata` — retrieval context, set with `opik_context.update_current_trace()`
- child `spans` — every sub-step decorated with `@opik.track`; full detail preserved

It also covers creating annotation queues programmatically and the post-hoc enrichment pattern for existing traces.

## Prerequisites

You need an Opik account to follow along — the value of this guide is watching the traces and the annotation queue render live in Opik.

| Variable | Description |
|---|---|
| `OPIK_API_KEY` | Opik API key |
| `OPIK_WORKSPACE` | Opik workspace name |

No LLM API key required — the example uses a mock retriever and mock LLM.

## Running it

Open the notebook in Colab (badge below), or run it locally in a uv-managed environment:

```bash
uv sync
uv run --with jupyter jupyter lab
```

Then open `annotation_queues_with_context.ipynb`.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/comet-ml/opik-examples/blob/main/guides/annotation_queues_with_context/annotation_queues_with_context.ipynb)

## How it works

The notebook builds a small traced RAG pipeline and walks through three things:

1. **Structuring the trace.** `rag_pipeline()` calls `retrieve()` and `generate()` (each `@opik.track`, so they become child spans), returns only the answer as `output`, and attaches the retrieved context as `metadata` via `opik_context.update_current_trace()`. Input and output stay clean; the supporting detail is one layer down.
2. **Creating a queue.** `client.create_traces_annotation_queue()` makes a review queue, `client.search_traces()` fetches the traces just logged, and `queue.add_traces()` adds them for review.
3. **Post-hoc enrichment.** For traces already logged without context, `client.update_trace()` adds metadata after the fact; `client.flush()` commits the writes before the traces are added to a queue.
