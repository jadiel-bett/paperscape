# Demo-paper selection and rights review

## Scope

Stage 1 defines the selection and rights-review process without downloading,
adding, or evaluating any real paper. PaperScape requires exactly three accepted
papers for the later evaluation baseline. One accepted paper is the primary
demo, and the accepted set spans at least two subject areas.

Up to two additional non-acceptance papers may be considered, for a hard maximum
of five manifest entries.

## Selection criteria

Each candidate must:

- have a clear research question;
- support at least three defensible findings and one stated limitation;
- contain selectable, page-aware text;
- be understandable without relying on complex figures for its central claims;
- avoid sensitive personal data;
- have a stable source URL;
- have a nonblank licence and licence-evidence URL;
- be suitable for the intended demonstration and evaluation use.

The primary demo paper must also be concise enough for a live walkthrough and
have evidence that non-specialist judges can understand from extracted text.

## Rights review

Do not add a real manifest entry or local PDF until a reviewer confirms:

1. the paper's licence;
2. the authoritative licence-evidence URL;
3. whether local PDF use is permitted;
4. whether source excerpts may be used in local results;
5. whether any generated excerpt-bearing artifact may be redistributed.

Open access does not automatically permit unrestricted redistribution or excerpt
reuse. Complete generated maps remain private unless the paper licence and
excerpt-use policy have been reviewed for the intended publication.

## Manifest contract

The manifest begins as:

```json
{
  "schema_version": 1,
  "papers": []
}
```

Each future paper entry records:

- `paper_id`
- `title`
- `authors`
- `source_url`
- `licence`
- `licence_evidence_url`
- `retrieved_on`
- `local_filename`
- `subject_area`
- `acceptance`
- `primary_demo`
- `expected_high_level_findings`
- `known_limitations`
- `selection_rationale`
- `rights_review.status`
- `rights_review.excerpt_use_reviewed`

The completed acceptance manifest must enforce:

- exactly three entries with `acceptance=true`;
- exactly one accepted entry with `primary_demo=true`;
- at least two subject areas among accepted entries;
- no more than five total entries;
- unique paper IDs, local filenames, and source URLs;
- basename-only local filenames with no absolute path, separator, or `..`;
- resolved local paths confined below `evals/live/papers`;
- approved rights status and excerpt-use review before any real entry is added.

## Local storage

Rights-approved PDFs belong only under ignored `evals/live/papers/`. Complete
maps and private review artifacts belong only under ignored
`evals/live/results/private/`. Sanitized, approved scorecards may be committed
outside the private results directory.
