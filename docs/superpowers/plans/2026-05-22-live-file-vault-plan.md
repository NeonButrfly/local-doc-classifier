# Live-File Vault Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make classifier notes carry canonical live-file metadata, preserve current attachment compatibility, and stop low-confidence review notes from coming out empty.

**Architecture:** Keep `90 Attachments` as a compatibility layer while shifting note metadata toward canonical live files. Implement the new contract in `write_obsidian_note`, add deterministic fallback summary/reason helpers, and validate the generated markdown directly through focused note-output tests.

**Tech Stack:** Python 3, unittest, filesystem-based note generation, Obsidian markdown output

---

### Task 1: Add note-output regression tests

**Files:**
- Create: `C:\Code\local-doc-classifier\tests\test_obsidian_note_output.py`
- Read: `C:\Code\local-doc-classifier\classifier\app\classify-to-obsidian.py`

- [ ] **Step 1: Write a failing metadata test**
- [ ] Assert a generated note includes:
  - `canonical_source_path`
  - `canonical_source_hash`
  - `last_seen_filename`
  - `attachment_mode`
  - `compatibility_attachment_path`
- [ ] **Step 2: Run**
  - `python -m pytest tests/test_obsidian_note_output.py -q`
- [ ] **Expected**
  - fail because the current note writer does not emit those fields

- [ ] **Step 3: Write a failing fallback-text test**
- [ ] Assert a low-confidence `unknown` classification with blank `summary` and blank `reason` still produces readable text in both sections.
- [ ] **Step 4: Run**
  - `python -m pytest tests/test_obsidian_note_output.py -q`
- [ ] **Expected**
  - fail because the current note writer emits empty sections

### Task 2: Implement the new note contract

**Files:**
- Modify: `C:\Code\local-doc-classifier\classifier\app\classify-to-obsidian.py`

- [ ] **Step 1: Add small helpers**
- [ ] Add helpers for:
  - summary fallback text
  - reason fallback text
  - compatibility attachment metadata serialization
- [ ] **Step 2: Update `write_obsidian_note`**
- [ ] Emit canonical metadata fields in frontmatter and keep the human-readable body stable.
- [ ] Keep current attachment copying behavior when `attach_originals=True`, but record it as compatibility mode.
- [ ] **Step 3: Add record fields**
- [ ] Extend the manifest record written after note generation so downstream consumers can read the same canonical metadata without reparsing only the note body.

### Task 3: Validate and keep compatibility

**Files:**
- Modify if needed: `C:\Code\local-doc-classifier\README.md`
- Test: `C:\Code\local-doc-classifier\tests\test_obsidian_note_output.py`

- [ ] **Step 1: Run focused tests**
  - `python -m pytest tests/test_obsidian_note_output.py -q`
- [ ] **Step 2: Run adjacent regression tests**
  - `python -m pytest tests/test_document_fast_path.py tests/test_spreadsheet_fast_path.py tests/test_image_label_policy.py -q`
- [ ] **Step 3: Update docs only if the note contract or operator expectations became externally visible**

