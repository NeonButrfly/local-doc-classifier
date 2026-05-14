---
title: Hybrid Classifier Autonomy Design
date: 2026-05-14
issue: 7
status: proposed
---

# Hybrid Classifier Autonomy Design

## Goal

Build a hybrid classification system that combines heuristics, LightGBM, and the LLM so the classifier stays fast on obvious cases, uses the public taxonomy-aware model when needed, and continuously improves from shadow-mode disagreement evidence.

## Non-Goals

- Do not pass the full public taxonomy into every LLM prompt.
- Do not let generated artifacts, queued jobs, or retraining outputs drift into git.
- Do not allow autonomous source-code rewriting from disagreement evidence.
- Do not regress the image safety policy or the existing Obsidian/API flows.

## Requirements

- Heuristics, LightGBM, and the LLM must all participate in the system.
- The live path must stay fast for obvious files.
- The model must still be used inline when the fast path is weak or taxonomy certainty is low.
- Shadow comparisons must run in the background through a queue-based workflow.
- Retraining and threshold updates should be autonomous.
- Heuristic updates should be autonomous only through config and learned artifacts, not source edits.
- The public taxonomy router must remain the source of candidate labels for model prompts.

## Architecture

### Live Path

1. Parser extracts content and structured metadata.
2. Heuristic layer produces:
   - proposed labels
   - feature hits
   - heuristic confidence
   - heuristic rule id or path
3. LightGBM layer produces:
   - label probabilities
   - `needs_llm` probability
   - disagreement-risk probability
4. Gating layer chooses:
   - fast return if heuristic and LightGBM align strongly
   - inline LLM if confidence is weak, disagreement risk is high, or taxonomy fit is unclear
5. Manifest stores all live decision details.
6. Queue job is emitted for background shadow validation when enabled.

### Background Path

1. Queue worker reads staged shadow jobs.
2. Worker runs taxonomy-aware LLM classification using candidate labels from the public taxonomy router.
3. Worker compares:
   - heuristic result
   - LightGBM result
   - live final result
   - shadow LLM result
4. Worker writes comparison records and disagreement summaries.
5. Autonomous retraining and threshold refresh jobs consume those records.

## Decision Modes

### Heuristic Fast Path

Use when:

- heuristic confidence is high
- LightGBM confidence is high
- both results align on the primary label
- disagreement-risk score is low

### Inline Model Path

Use when any of the following is true:

- heuristic confidence falls below threshold
- LightGBM `needs_llm` exceeds threshold
- heuristic and LightGBM disagree on the primary label
- candidate taxonomy branch is broad or ambiguous
- parser indicates OCR-heavy or low-text extraction

### Shadow Comparison Path

Run in background for:

- all live classifications initially
- later, configurable sampling for stable categories

Shadow mode never changes source code. It records evidence and can optionally mark items for review or correction workflows.

## Components

### Classifier Pipeline

Extend `classifier/app/classify-to-obsidian.py` with:

- heuristic feature extraction helpers
- LightGBM prediction helpers
- hybrid gating logic
- shadow job emission
- richer manifest timing and decision metadata

### API

Extend `classifier/app/api_server.py` with:

- support for hybrid/shadow mode configuration passthrough
- surfacing hybrid decision metadata
- optional queue/worker health visibility if needed

### Config

Add config-driven artifacts such as:

- `config/hybrid-gating.json`
- `config/heuristic-rules.json`
- `config/lightgbm-classifier.joblib`
- `config/lightgbm-training-report.json`

These configs are the only autonomous heuristic-update targets.

### Queue / Shadow Records

Use output-side runtime artifacts such as:

- `output/shadow-queue/`
- `output/shadow-comparisons.jsonl`
- `output/retrain/`

These remain generated runtime data and must stay ignored by git.

### Training

Train LightGBM on:

- extracted text summaries
- filename and extension
- parser choice
- heuristic features and confidence
- taxonomy-router candidates
- correction-memory examples
- accepted final labels
- high-confidence shadow LLM labels where allowed

Targets:

- primary label
- `needs_llm`
- disagreement risk

## Autonomous Update Loop

### Safe Autonomous Updates

Allowed automatically:

- LightGBM model retraining
- threshold tuning in `hybrid-gating.json`
- heuristic rule weight updates in `heuristic-rules.json`
- disagreement report generation

Not allowed automatically:

- source-code edits
- taxonomy file overwrites without explicit backup flow
- silent changes to correction memory semantics

### Promotion Rules

Only promote disagreement-derived updates when:

- enough examples accumulate
- shadow LLM confidence is above a strict threshold
- disagreement pattern is repeated
- correction history does not contradict the change

## Taxonomy Use

The public taxonomy router remains the narrowing mechanism. The model prompt should receive:

- top candidate categories from the taxonomy router
- heuristic proposed labels
- relevant correction examples

It must not receive the full taxonomy list every time.

## Testing

Add tests for:

- heuristic feature extraction
- LightGBM gating decisions
- inline-versus-fast routing
- shadow comparison emission
- disagreement record format
- autonomous config-only updates
- regression coverage for PDF, DOCX, XLSX, and image policy behavior

## Deployment

1. Update repo and push to `main`.
2. Redeploy `192.168.50.196`.
3. Update `192.168.50.232`.
4. Validate:
   - live latency
   - shadow job creation
   - shadow comparison records
   - LightGBM artifact generation
   - no token leakage

## Risks

- Over-trusting shadow LLM outputs can bake in model mistakes.
- Aggressive auto-updates can cause config thrash.
- Queue growth can mask failures if worker health is not visible.
- Taxonomy drift can destabilize label routing if not versioned in reports.

## Recommendation

Implement this in phases:

1. Hybrid gating and richer manifest records
2. Shadow queue and comparison artifacts
3. LightGBM training and live routing integration
4. Autonomous config updates from disagreement evidence

This keeps the system safe while moving toward full autonomous improvement.
