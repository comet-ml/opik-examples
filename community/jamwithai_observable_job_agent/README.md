# Observable Job Agent

A community showcase of [Observable Job Agent](https://github.com/jamwithai/observable-job-agent),
an open-source project by Shirin Khosravi Jam (jamwithai). We link to it here to
spotlight how the community uses Opik — the code lives in the author's repo.

## What I built
An MIT-licensed AI job-matching agent you run locally: upload a CV (PDF) and it
produces a typed profile, searches real job listings across multiple sources, and
ranks each posting with a 0–100 fit score plus an explanation of matches and gaps.
It is built on LangGraph (agent graph + a bounded reformulation loop) with a Gradio
three-step wizard, and it's Part 1 ("Build") of a "Build → Evaluate → Self-Improve"
series.

## Problem it solves
Job seekers waste hours manually judging whether a posting fits their background.
This agent turns that into a structured, explainable ranking — and does it in a way
whose cost, latency, and quality are measurable, so the agent can later be evaluated
and improved rather than trusted blindly.

## What I learned
The project's thesis is that observability comes first: the agent is instrumented
*before* it is made good, so cost, latency, and quality are measurable from run one.
That ordering makes Opik a design tool, not an afterthought — the span tree and
agent graph reveal how each node behaves as the graph evolves.

## How I used Opik
Opik (Comet) provides a span tree per LangGraph node, an auto-drawn agent graph, and
per-run cost tracking; each run attaches the uploaded CV plus metadata (git SHA,
model, job counts) and tags, and prompts are registered and versioned in Opik's
prompt library. The Gradio run footer surfaces cost, latency, and a trace link. See
the author's Opik setup and tracing guide:
https://github.com/jamwithai/observable-job-agent/blob/main/docs/opik_setup.md
