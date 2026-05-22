# Live-File Vault Output Design

Related issue: #11

## Goal

Make classifier output more stable and more human-usable by treating notes as
metadata over canonical live files instead of treating copied vault attachments
as the long-term source of truth.

## Current State

- The classifier writes notes into the live vault at
  `\\kayraspi2\cloud-vault\local-doc-classifier-vault`.
- It creates copied attachments under `90 Attachments` and links notes to those
  copies.
- Recent live sampling showed too many `unknown` notes with blank summary or
  blank reason fields, which makes the review queue noisy and harder to trust.

## Approved Approach

Use a compatibility-first note format.

- Keep the live vault path unchanged.
- Keep `90 Attachments` for compatibility in this first pass.
- Extend note output so each note records canonical source metadata that points
  back to the live mirrored file.
- Improve low-confidence fallback text so review notes stay readable even when
  the classifier is unsure.

## Non-Goals For This Pass

- No removal of `90 Attachments`.
- No requirement that Obsidian directly open external filesystem links yet.
- No vault move into the iCloud mirror tree.
- No bidirectional sync dependency.

## Note Contract Changes

Each note should carry enough metadata for future repair and current human use:

- canonical source path
- canonical source hash
- last-seen filename
- attachment mode
- compatibility attachment link path when the attachment copy exists

The note body should remain readable in Obsidian even before any future
reconciler has touched it.

## Output Quality Changes

Weak classifications should not produce empty-looking notes.

- If summary generation is blank, emit a short fallback summary based on the
  source filename and the classifier confidence state.
- If reason text is blank, emit a concise fallback explanation that the file was
  routed for review because the classifier could not make a confident decision.
- `unknown` notes should read as explicit review items, not as finished
  classification output.

## Attachment Strategy

For this pass, copied attachments remain a compatibility layer.

- Existing note behavior should keep working.
- New metadata should make it clear that the copied attachment is not the
  canonical source of truth.
- Future cleanup can replace or remove compatibility attachments once the
  reconciler and sync architecture are proven.

## Failure Handling

- If the source hash is unavailable, still write the note and mark the metadata
  accordingly.
- If an attachment copy is unavailable, still write the note with canonical
  source metadata and a clear compatibility note.
- If fallback text is needed, prefer consistent plain language over empty
  fields.

## Testing

- unit tests for note metadata fields
- unit tests for fallback summary generation
- unit tests for fallback reason generation
- regression tests proving attachment links still render in the existing vault
  layout
- sample-output validation for `unknown` notes so review files remain useful

## Rollout Notes

This design keeps the classifier safe to deploy into the current vault while
preparing a better long-term model:

- notes describe canonical live files
- copied attachments remain temporary compatibility artifacts
- low-confidence notes become easier to review instead of harder to trust
