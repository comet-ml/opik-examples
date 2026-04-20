# opik-examples

Code snippets and examples for working with [Opik](https://www.comet.com/site/products/opik/), Comet's LLM evaluation and observability platform.

## Structure

```
opik-examples/
├── code-snippets/     # Short, self-contained scripts for specific tasks
└── examples/          # Multi-file, end-to-end examples with full context
```

### code-snippets

| Snippet | Description |
|---------|-------------|
| [trace_management](code-snippets/trace_management/) | Inspect and delete traces by date range, tags, or per-tag TTL policies |
| [automate_annotation_queue](code-snippets/automate_annotation_queue/) | Automatically route traces into annotation queues via batch or real-time assignment |

### examples

| Example | Description |
|---------|-------------|
| [otel_with_offline_eval_example](examples/otel_with_offline_eval_example/) | Use OpenTelemetry tracing alongside Opik's offline evaluation workflow |
| [programmatic_leaderboard_dashboard_creation](examples/programmatic_leaderboard_dashboard_creation/) | Create an Experiment Leaderboard dashboard entirely via the REST API |

