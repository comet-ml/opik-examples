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
| [trace_deletion](code-snippets/trace_deletion/) | Bulk-delete traces older than N months across one or more projects |

### examples

| Example | Description |
|---------|-------------|
| [otel_with_offline_eval_example](examples/otel_with_offline_eval_example/) | Use OpenTelemetry tracing alongside Opik's offline evaluation workflow |
| [programmatic_leaderboard_dashboard_creation](examples/programmatic_leaderboard_dashboard_creation/) | Create an Experiment Leaderboard dashboard entirely via the REST API |

