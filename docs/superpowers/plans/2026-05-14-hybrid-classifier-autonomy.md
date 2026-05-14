# Hybrid Classifier Autonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a hybrid classifier that combines heuristics, LightGBM, and taxonomy-aware LLM routing, then adds autonomous shadow comparisons, background retraining, and config-only heuristic tuning.

**Architecture:** Keep the existing fast-path parsers, but route every classification through a hybrid decision layer. That layer fuses heuristic confidence, LightGBM predictions, and taxonomy-router candidates to decide whether to return fast or call the LLM inline, while a background file-queue worker performs shadow comparisons and retrains/update configs from disagreement evidence.

**Tech Stack:** Python, FastAPI, requests, scikit-learn, LightGBM, filesystem queue, JSONL runtime artifacts

---

### Task 1: Add Hybrid Runtime Config and Tests

**Files:**
- Create: `classifier/app/hybrid_runtime.py`
- Create: `tests/test_hybrid_runtime.py`
- Create: `config/hybrid-gating.json`
- Create: `config/heuristic-rules.json`

- [ ] **Step 1: Write the failing tests**

```python
def test_choose_live_decision_prefers_fast_path_when_heuristic_and_model_align():
    ...

def test_choose_live_decision_requires_llm_on_confidence_conflict():
    ...

def test_build_shadow_record_marks_disagreement():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m unittest tests.test_hybrid_runtime -v`
Expected: FAIL with missing module/functions

- [ ] **Step 3: Write minimal hybrid runtime implementation**

```python
def choose_live_decision(...):
    ...

def build_shadow_record(...):
    ...
```

- [ ] **Step 4: Add default gating and heuristic config files**

```json
{
  "mode": "hybrid",
  "heuristic_fast_confidence": 0.92,
  "lightgbm_fast_confidence": 0.80,
  "needs_llm_threshold": 0.45,
  "disagreement_risk_threshold": 0.35,
  "shadow_mode": "all"
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3 -m unittest tests.test_hybrid_runtime -v`
Expected: PASS

### Task 2: Add LightGBM Training and Prediction

**Files:**
- Modify: `classifier/app/hybrid_runtime.py`
- Create: `tests/test_lightgbm_training.py`
- Create: `classifier/app/retrain_hybrid_model.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_train_lightgbm_model_writes_model_and_report():
    ...

def test_predict_lightgbm_result_returns_top_label_and_gate_scores():
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3 -m unittest tests.test_lightgbm_training -v`
Expected: FAIL with missing training/prediction helpers

- [ ] **Step 3: Implement feature extraction, LightGBM training, and prediction**

```python
def build_training_examples(...):
    ...

def train_lightgbm_model(...):
    ...

def predict_lightgbm_result(...):
    ...
```

- [ ] **Step 4: Add retraining CLI entrypoint**

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3 -m unittest tests.test_lightgbm_training -v`
Expected: PASS

### Task 3: Wire Hybrid Routing into Classification

**Files:**
- Modify: `classifier/app/classify-to-obsidian.py`
- Modify: `tests/test_document_fast_path.py`
- Modify: `tests/test_spreadsheet_fast_path.py`
- Modify: `tests/test_upload_benchmark_api.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_fast_path_uses_inline_model_when_gate_requires_llm():
    ...

def test_fast_path_records_hybrid_decision_metadata():
    ...
```

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `py -3 -m unittest tests.test_document_fast_path tests.test_spreadsheet_fast_path tests.test_upload_benchmark_api -v`
Expected: FAIL on missing hybrid metadata/gating behavior

- [ ] **Step 3: Implement hybrid decision flow in classifier**

```python
heuristic_result = ...
lightgbm_result = ...
decision = choose_live_decision(...)
if decision["use_inline_llm"]:
    classification = classify_markdown(...)
else:
    classification = heuristic_result
```

- [ ] **Step 4: Add manifest and timing metadata for hybrid decisions**

```python
timing["hybrid"] = {...}
record["hybrid"] = {...}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3 -m unittest tests.test_document_fast_path tests.test_spreadsheet_fast_path tests.test_upload_benchmark_api -v`
Expected: PASS

### Task 4: Add Shadow Queue and Background Processing

**Files:**
- Modify: `classifier/app/hybrid_runtime.py`
- Modify: `classifier/app/api_server.py`
- Create: `tests/test_shadow_processing.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_enqueue_shadow_job_writes_queue_file():
    ...

def test_process_shadow_queue_writes_comparison_record():
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3 -m unittest tests.test_shadow_processing -v`
Expected: FAIL with missing queue helpers

- [ ] **Step 3: Implement queue writer and processor**

```python
def enqueue_shadow_job(...):
    ...

def process_shadow_queue_once(...):
    ...
```

- [ ] **Step 4: Start background worker loop from API server**

```python
threading.Thread(target=shadow_worker_loop, daemon=True).start()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3 -m unittest tests.test_shadow_processing -v`
Expected: PASS

### Task 5: Add Autonomous Retraining and Config-Only Heuristic Updates

**Files:**
- Modify: `classifier/app/hybrid_runtime.py`
- Create: `tests/test_autonomous_updates.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_apply_disagreement_updates_adjusts_thresholds():
    ...

def test_process_shadow_queue_triggers_retrain_when_threshold_is_met():
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3 -m unittest tests.test_autonomous_updates -v`
Expected: FAIL with missing update helpers

- [ ] **Step 3: Implement config-only autonomous updates**

```python
def apply_disagreement_updates(...):
    ...

def maybe_retrain_from_shadow_data(...):
    ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3 -m unittest tests.test_autonomous_updates -v`
Expected: PASS

### Task 6: Docs, Deployment, and Live Validation

**Files:**
- Modify: `docs/API.md`
- Modify: `docs/FIXTURE_TESTING.md`

- [ ] **Step 1: Update docs for hybrid mode, shadow queue, and autonomous retraining**

```md
- hybrid live decisions
- shadow comparison artifacts
- background retraining behavior
```

- [ ] **Step 2: Run the full local test suite**

Run: `py -3 -m unittest tests.test_hybrid_runtime tests.test_lightgbm_training tests.test_shadow_processing tests.test_autonomous_updates tests.test_document_fast_path tests.test_spreadsheet_fast_path tests.test_upload_benchmark_api tests.test_image_label_policy -v`
Expected: PASS

- [ ] **Step 3: Redeploy the live server and update the Pi checkout**

Run:
- update `192.168.50.196`
- update `192.168.50.232`

Expected: API health passes and new artifacts are live

- [ ] **Step 4: Validate live behavior**

Run:
- fast fixture uploads
- shadow queue creation
- shadow comparison generation
- retraining artifact generation

Expected: live classifications succeed, shadow records appear, and no token leakage occurs

## Self-Review

- Spec coverage: hybrid gating, LightGBM, taxonomy-aware model usage, shadow queue, autonomous config updates, tests, docs, and deployment are all mapped to tasks.
- Placeholder scan: commands, files, and code targets are explicit enough to execute inline.
- Type consistency: the same helper names and artifact names are reused across tasks.
