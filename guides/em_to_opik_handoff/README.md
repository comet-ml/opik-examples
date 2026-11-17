# Road-obstruction triage: fine-tuning in Comet EM, evaluation in Opik

A reusable end-to-end demo for vision + LLM teams. A vehicle flags a possible road blockage;
a fine-tuned object detector and a vision-language model decide whether the road ahead is
`blocked`, `partial` or `clear`.

What it shows:

- **Comet Experiment Management**: a real YOLO fine-tune with loss and mAP curves,
  hyperparameters, confusion matrix, image predictions, system metrics, a versioned dataset
  Artifact and a Model Registry entry.
- **Opik**: traces of the inference pipeline (detector span + vision-model span, with images),
  a dataset with human ground truth, offline experiments comparing two pipeline variants, an
  LLM judge, a human annotation queue with agreement numbers, a versioned prompt, and an
  optional online evaluation rule.
- **The handoff between the two**: the same identifiers are visible in both products, with
  links in both directions.

## The handoff

`scripts/03_register.py` writes `handoff.json`. It is the only thing the Opik side knows about
the training side.

| Identifier | Where it shows in Comet EM | Where it shows in Opik |
|---|---|---|
| Experiment key and URL | The experiment itself | Detector span metadata, trace metadata (`em_url`), experiment configuration |
| Registry model and version | Model Registry page, linked to the experiment | Trace tag `detector:<model>:<version>`, span metadata, experiment configuration, experiment name |
| Dataset artifact version | Artifacts tab and experiment lineage | Experiment configuration, dataset description |
| Opik experiment URLs and scores | "Other" and "Metrics" tabs, HTML tab with clickable links | The experiments themselves |

The pipeline loads its weights from the Model Registry, not from the local training folder, so
what Opik evaluates is what the registry serves.

## Setup

Requirements: [uv](https://docs.astral.sh/uv/), a Comet account (EM + Opik), an Anthropic API
key, about 25 GB of free disk. Training runs on an Apple Silicon GPU by default
(`--device mps`); pass `--device 0` for CUDA or `--device cpu`.

```bash
uv sync
```

```bash
cp .env.example .env
```

Fill in the keys and workspace names in `.env`. All project, model and dataset names are set
there too, so two people can run the demo side by side in one workspace.

Download the dataset (CMU ROADWork, see Attribution). Only two files are needed:

```bash
mkdir -p data/raw/roadwork && cd data/raw/roadwork && curl -L -C - -o images.zip https://ndownloader.figshare.com/files/47217577 && curl -L -o annotations.zip https://ndownloader.figshare.com/files/47217703 && unzip -q annotations.zip
```

## Run order

| Step | Command | What it does | Time |
|---|---|---|---|
| 1 | `uv run python scripts/01_prepare_data.py` | Unzips images, converts COCO labels to YOLO, builds the held-out verdict eval set | 5 min |
| 2 | `uv run python scripts/02_train.py --epochs 15` | Fine-tunes YOLO11s, tracked in Comet EM, logs the dataset Artifact | about 4 min per epoch on an M4 Max (default is 30 epochs) |
| 3 | `uv run python scripts/03_register.py` | Registers the `baseline` training run (`--name` for another), writes `handoff.json`, verifies the registry download | 1 min |
| 4 | `uv run python scripts/04_build_opik_dataset.py` | Creates the Opik dataset with images and human labels | 2 min |
| 5 | `uv run python scripts/05_run_experiments.py` | Runs `vlm_only` and `detector_vlm` experiments, links results back to EM | 10 min |
| 6 | `uv run python scripts/06_review_queue.py` | Samples 10 percent of traces into an annotation queue | 1 min |
| 7 | `uv run python scripts/07_agreement.py` | Human vs model and judge vs human agreement (after annotating in the UI) | 1 min |
| 8 | `uv run python scripts/08_online_rule.py` | Optional: online LLM judge rule | 1 min |
| 9 | `uv run python scripts/09_simulate_traffic.py` | Optional: fresh traffic for the rule to score | 3 min |

Quick iteration: `scripts/02_train.py --epochs 1 --name smoke`,
`scripts/04_build_opik_dataset.py --limit 20`,
`scripts/05_run_experiments.py --dataset roadwork-verdicts-v1-dev`.
Subset and dev-dataset runs are named `<variant>-<version>-dev`, so they never mix with the
full run that the gate and the Comet back-link read.
Before a model is registered the pipeline runs on stock `yolo11s.pt` and tags traces
`detector:yolo11s-stock:dev-stock`.

The online rule's judge runs inside Opik, not on your machine. `ONLINE_JUDGE_MODEL` in `.env`
picks the model: `opik-free-model` needs no setup; for a Claude judge add an Anthropic key under
Opik -> Configuration -> AI Providers and set the model name there. Skip steps 8 and 9 where
online evaluation is not allowed; nothing else depends on them.

`uv run python scripts/reset_dev.py` removes dev-stock traces, `-dev` experiments with their
traces and the dev dataset from the Opik project, so the demo shows only the full runs on the
registered model. Add `--queue` to
also delete the review queue (this discards annotations made in it).

Re-running is safe: registration is skipped if the experiment is already registered, the
dataset artifact is reused only when the labels are unchanged, the Opik dataset is kept in
step with the eval manifest, the review queue is only topped up to its target size, and
results are linked back to Comet EM only for a full run on the default dataset. Re-running
step 5 in full creates a second experiment with the same name; the gate reads the newest.

Tests: `uv run pytest`.

## Demo script (about 13 minutes)

1. **Framing (1 min).** A sensor flags a possible blockage. Today a person reviews footage.
   The goal: automate the first pass, keep humans on a 10 percent sample.
2. **Comet EM (3 min).** Open the training experiment: mAP and loss curves, hyperparameters,
   confusion matrix, image predictions with boxes, system metrics, the dataset Artifact.
3. **Model Registry (1 min).** The registered version and its source experiment. Note the
   version string.
4. **Opik traces (3 min).** Filter by tag `detector:<model>:<version>`. Open a trace: the
   detector span (overlay image, metadata with the experiment key and `em_url`), then the
   verdict span (input image, structured verdict, tokens and cost).
5. **Opik experiments (2.5 min).** Compare `vlm_only-<version>` and `detector_vlm-<version>` on
   the same dataset. Open an item where they disagree. The experiment configuration shows the
   same model version, dataset artifact and prompt version.
6. **Human review (1.5 min).** Open the annotation queue, annotate one trace live. Back in the
   traces table, show the human and judge columns side by side and the agreement numbers from
   `scripts/07_agreement.py`.
7. **Online evaluation (1 min, optional).** The rule definition, then fresh traces tagged
   `source:simulated-traffic` that were scored with no script involved.
8. **Close the loop (0.5 min).** Back in Comet EM: the experiment now carries the Opik
   experiment links and verdict accuracy. Show the loop below.

For an offline-only audience, skip step 7.

## The retrain loop

```
  human / model disagreements (annotation queue)
                 |
                 v
  new labelled frames -> dataset Artifact v1.1.0 (Comet)
                 |
                 v
  retrain -> new EM experiment -> candidate registry version
                 |
                 v
  offline Opik experiment on the same verdict dataset
                 |
                 v
  gate: candidate must beat current  ->  promote | hold
                 |
                 v
  handoff.json points at the promoted version
```

The gate is `uv run python -m roadwork_demo.gate <candidate_experiment> <current_experiment>`.
The demo runs one pass of the loop (one training run); the pieces for the second pass are in
place but not executed.

## Layout

```
src/roadwork_demo/   config + handoff, data conversion, images, pipeline, metrics, agreement, gate
scripts/             numbered stages, run in order
prompts/             verdict and judge prompts (the verdict prompt is versioned in Opik)
tests/               unit tests for the pure logic
docs/                design spec and implementation plan
```

## Known limits

- Single frames only. Whether a blockage is short-lived or lasts hours needs video or repeated
  observations; that is the natural next step.
- Work-zone objects only (cones, drums, barriers, barricades, work-zone signs and so on), not
  general traffic signs.
- Ground-truth verdicts are derived from ROADWork's human scene tags (`travel_alteration`):
  `Fully Blocked` -> blocked, exactly `Partially Blocked` -> partial, exactly `None` -> clear.
  The `Fully Blocked` tag also covers closed sidewalks and side streets, so a frame counts as
  blocked only if its human-written scene description says the road itself is closed (see
  `describes_own_road_closed` in `src/roadwork_demo/data.py`). Some label noise remains.
- The eval frames come from the detector's validation split: never trained on, but they were
  used for model selection during training.
- Links stored in Opik trace metadata (`em_url`) may show as plain text; copy the experiment
  key into Comet, or use the clickable links on the Comet side (HTML tab).
- The "clear" class is small (29 held-out frames), so per-class accuracy for it moves in large
  steps.

## Attribution

Images and annotations come from the **ROADWork dataset** (Carnegie Mellon University),
https://kilthub.cmu.edu/articles/dataset/ROADWork_Data/26093197 , released under the Open Data
Commons Attribution License v1.0. Please cite the ROADWork paper when using it. This repository
does not redistribute the dataset; it only contains scripts that download and convert it.
