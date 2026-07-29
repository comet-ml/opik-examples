# Building a Coding Agent from Scratch (course)

A community showcase of [Building a Coding Agent from Scratch](https://github.com/decodingai-magazine/building-a-coding-agent-from-scratch-course),
an open-source course by Paul Iusztin (Decoding AI). We link to it here to spotlight
how the community uses Opik — the code lives in the author's repo.

## What I built
A project-based, Apache-2.0 course that walks engineers from a ~20-line agent loop
to cloud-deployed subagent swarms. Across eight lessons it builds "the harness"
around a coding agent — permissions, sandboxes, context compaction, subagent
fan-out, a durable runtime, and evals — on a Pydantic AI ReAct loop with
file/bash/web/LSP tools and Docker/Modal sandboxes.

## Problem it solves
Most agent tutorials stop at the model call. This course targets the harder,
production-shaped problem: the engineering *around* the model that makes a coding
agent safe, observable, and reliable — the part teams actually have to build.

## What I learned
Opik is wired in as an `observability/` module so every session is traced, with
secrets scrubbed before they reach a log. Lesson 7 ("Benchmarks, regression probes,
and online evals") shows how tracing feeds an eval suite, making agent behavior
measurable rather than anecdotal as the harness grows.

## How I used Opik
Each agent session is traced end-to-end (Opik threads), and the course's eval suite
runs benchmarks, regression probes, and online evals against those traces. Opik
(Comet) is a course sponsor and runs on the free tier. See the author's Opik
threads screenshot:
https://github.com/decodingai-magazine/building-a-coding-agent-from-scratch-course/blob/main/assets/opik-threads.png
