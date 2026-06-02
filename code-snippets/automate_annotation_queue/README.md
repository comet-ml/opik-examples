# Automating Annotation Queues in Opik

`auto_annotate.py` shows two patterns for automatically routing traces into Opik annotation queues — a nightly batch job and a real-time approach that enqueues traces inline as they are created.

## Prerequisites

```bash
pip install -r requirements.txt
```

Configure your Opik credentials:

```bash
export OPIK_API_KEY=your-api-key
export OPIK_WORKSPACE=your-workspace
```

Or run `opik configure` to set them interactively.

## Methods

### Method 1 — Batch assignment (scheduled job)

Fetches traces from a project, optionally filters them (e.g. by a low feedback score), and distributes them across annotation queues in round-robin order. Intended to run once a day via cron or a workflow scheduler.

```
┌─────────────┐        ┌──────────────────┐
│  Opik traces │──────▶│  batch_assign_   │
│  (project)  │        │  traces_to_queues│
└─────────────┘        └────────┬─────────┘
                                │ round-robin
               ┌────────────────┼────────────────┐
               ▼                ▼                ▼
         Queue - Team A   Queue - Team B   Queue - Team C
```

**To run:**

```bash
# In auto_annotate.py, set option = 1 (already the default)
python auto_annotate.py
```

The script will:
1. Seed a small set of sample traces into the `test-annotate` project (first run only).
2. Create three annotation queues if they don't already exist.
3. Fetch all traces, shuffle them, and distribute evenly across the queues.

**Filtering traces before assignment**

Uncomment and edit the `filter_string` inside `batch_assign_traces_to_queues` to narrow which traces are enqueued:

```python
traces = client.search_traces(
    project_name=PROJECT_NAME,
    filter_string="feedback_scores.user_satisfaction < 0.6",
)
```

### Method 2 — Real-time assignment (inline with inference)

Adds each trace to an annotation queue immediately after the LLM call completes, using `opik_context.get_current_trace_data()` to access the live trace ID before the trace flushes.

```
my_llm_call()
  │
  ├─ simulated_llm_call()   ← your LLM call goes here
  │
  └─ get_current_trace_data()
       │
       └─ queue.add_traces([trace])   ← enqueued immediately
```

**To run:**

```python
# In auto_annotate.py, set option = 2
python auto_annotate.py
```

**Adapting to your own LLM call:**

Replace `simulated_llm_call` with your actual model invocation and decorate the top-level function with `@track(project_name=PROJECT_NAME)`:

```python
@track(project_name=PROJECT_NAME)
def my_llm_call(user_input: str, annotation_queue_name: str) -> str:
    response = your_model.invoke(user_input)   # ← your call here

    trace_data = opik_context.get_current_trace_data()
    if trace_data is not None:
        client = opik.Opik()
        queue = get_or_create_queue(client, annotation_queue_name)
        trace = client.get_trace_content(trace_data.id)
        queue.add_traces([trace])

    return response
```

## Choosing a method

| | Method 1 (Batch) | Method 2 (Real-time) |
|---|---|---|
| **When traces are enqueued** | Once per scheduled run | As each trace is created |
| **Best for** | Reviewing historical traces, post-hoc quality checks | Flagging traces for immediate human review |
| **Scheduling** | Cron / workflow scheduler | Inline — no separate job needed |
| **Filtering** | `search_traces` filter string | Custom logic inside the tracked function |

## Customisation

| What to change | Where |
|---|---|
| Project name | `PROJECT_NAME` constant at the top of the file |
| Queue names & instructions | `queue_configs` list in `batch_assign_traces_to_queues` |
| Feedback score dimensions | `feedback_definition_names` when creating a queue |
| Trace filter | `filter_string` argument in `client.search_traces` |
| LLM call | Replace `simulated_llm_call` with your own tracked function |
