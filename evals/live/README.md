# Live evaluation workspace

This directory is Stage 1 scaffolding only. It contains no papers, live results,
credentials, evaluator, or authorization to run paid watsonx calls.

## Local-only paths

- Put rights-approved local PDFs under `papers/`.
- Put complete maps, generated JSON or Markdown, prompts, raw SDK output, and
  private reviewer material under `results/private/`.
- Do not commit files from either local-only path.

Sanitized schemas, examples, and approved scorecards may be committed outside
`results/private/` after licence and excerpt-use review.

## Manifest readiness

`paper_manifest.json` intentionally starts with an empty `papers` list. Do not
add a real entry until its rights review is approved. A ready acceptance manifest
must have exactly three accepted papers, exactly one accepted primary demo, and
at least two accepted-paper subject areas. It may contain no more than five
papers in total.

The manifest records local basenames only. Absolute paths, path separators,
`..`, duplicate paper IDs, duplicate filenames, and duplicate source URLs are
not permitted.

Open access does not automatically authorize unrestricted redistribution or
excerpt reuse.

## Paid execution

There is no live evaluator in Stage 1. The Tier A pytest harness remains skipped
unless both paid-test gates are explicitly enabled, and paid Tier A execution
remains blocked until the retry/cost decision in the approved plan is recorded.
