<p align="center">
<img width="924" height="290" alt="image" src="https://github.com/user-attachments/assets/51a31b97-4fe5-4f93-805e-9933c1fb98e4" />
</p>

# opik-examples
Examples and utilities for working with [Opik](https://www.comet.com/site/products/opik/), Comet's LLM evaluation and observability platform.

## Structure

```
opik-examples/
├── integrations/   # Adding Opik to a specific framework or library
├── guides/         # How-to examples for Opik workflows and patterns
├── use-cases/      # End-to-end applications and domain workflows
├── scripts/        # Utility automations and API helpers
└── templates/      # Starter templates (use-case-template, script-template)
```

## Integrations

Examples for teams using a specific framework who want to add Opik.

| | Description |
|---|---|
| [integrations/otel/offline_evaluation](integrations/otel/offline_evaluation/) | OTel tracing alongside Opik's offline evaluation workflow |
| [integrations/otel/distributed_tracing](integrations/otel/distributed_tracing/) | Stitch out-of-process tool call spans into a single trace |

## Guides

Task-oriented examples for specific Opik workflows and patterns.

| | Description |
|---|---|
| [guides/annotation_queues_with_context](guides/annotation_queues_with_context/) | Structure RAG traces for Opik annotation queues — clean answer in output, context in metadata, full detail in child spans |
| [guides/tracing_finetuned_models](guides/tracing_finetuned_models/) | Fine-tune a model, register it to the CometML Model Registry, then fetch and trace inference in Opik |

## Use Cases

End-to-end applications and domain-specific workflows.

| | Description |
|---|---|
| [use-cases/call_summarizer](use-cases/call_summarizer/) | Streamlit app that summarises customer calls using an LLM, traced with Opik |
| [use-cases/governance_observability](use-cases/governance_observability/) | Instrument agents with governance metadata, derive composite metrics, and extract scores for oversight reporting |

## Scripts

Standalone scripts for automating and managing Opik resources.

| | Description |
|---|---|
| [scripts/trace_management](scripts/trace_management/) | Inspect and delete traces by date range, tags, or TTL policies |
| [scripts/automate_annotation_queue](scripts/automate_annotation_queue/) | Route traces into annotation queues via batch or real-time assignment |
| [scripts/usage_stats](scripts/usage_stats/) | Fetch trace and span counts per project and visualise trends |
| [scripts/leaderboard_dashboard](scripts/leaderboard_dashboard/) | Create an Experiment Leaderboard dashboard via the REST API |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution guide and example template.
