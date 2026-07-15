# PaperScape — Product Specification

## 1. Product Overview

PaperScape is an AI-powered research communication studio that transforms dense research PDFs into audience-specific, evidence-backed explainer packs.

The product helps users understand a paper, identify its most important claims, adapt those claims for a chosen audience, and create reusable communication assets without losing traceability to the original source.

PaperScape is not intended to replace researchers, reviewers, educators, or science communicators. It provides a grounded first draft that users can inspect, edit, approve, and export.

### Product vision

Make credible research easier to explain without separating the explanation from its evidence.

### MVP product promise

A user can upload one selectable-text academic PDF, generate a structured research map, choose an audience, and receive an editable explainer pack whose major factual claims link back to source excerpts and page numbers.

### First delivery milestone

The first vertical slice proves the foundational pipeline:

1. Upload a selectable-text PDF.
2. Extract page-aware chunks.
3. Start research-map generation as a background job.
4. Use IBM Granite through watsonx.ai.
5. Poll the job until completion.
6. Display the research question, exactly three findings, limitations, confidence labels, and source evidence.

Audience adaptation and full explainer-pack generation build on this foundation after the vertical slice is stable.

---

## 2. Target Users

### Primary users

#### Student researchers and research teams

They need to present papers during coursework, journal clubs, thesis reviews, STEM events, and project demonstrations, but may lack science-communication and visual-design experience.

#### Science communicators

They need to convert technical findings into public-facing summaries, scripts, posts, and visual explainers while preserving accuracy and source traceability.

#### Lecturers and STEM educators

They need fast, audience-appropriate teaching materials that explain unfamiliar papers without hiding methods, uncertainty, or limitations.

### Secondary users

- STEM clubs and science outreach groups
- Museum and exhibition educators
- Laboratory and innovation teams
- Non-profit and community-development organizations communicating research
- Policy and programme teams reviewing technical evidence

### Initial supported audiences

The MVP supports:

- High school learner
- General public
- Undergraduate STEM student

Later versions may support policymakers, sponsors, community workers, domain experts, and custom audience profiles.

---

## 3. Problem Statement

Research papers contain valuable knowledge but are usually optimized for expert review rather than public understanding. They use technical vocabulary, dense structures, domain-specific assumptions, tables, figures, and cautious scientific language.

Turning one paper into a clear summary, presentation outline, visual abstract, or narration script requires:

- Understanding the research question and methodology
- Separating findings from speculation
- Identifying limitations and uncertainty
- Adapting language to a particular audience
- Verifying statements against the source
- Designing a coherent story

This process is slow and requires research literacy, writing skill, and often visual or media-production experience.

Existing summarization tools commonly return a single generic summary. They may omit limitations, flatten uncertainty, lose page-level traceability, or attach citations after generation rather than building the explanation from verified evidence.

PaperScape addresses this gap by combining structured research understanding, audience adaptation, creative output generation, and evidence linking in one human-reviewed workflow.

---

## 4. Core Value Proposition

PaperScape helps users turn research into understandable and trustworthy communication assets faster.

Its core value is built on four principles:

1. **Grounded:** Major factual claims are linked to source chunks, page numbers, and excerpts.
2. **Audience-specific:** The same research can be explained differently for a learner, the general public, or a STEM student.
3. **Creative:** The output is a reusable explainer pack rather than a single summary.
4. **Human-controlled:** Users review, edit, approve, exclude, or regenerate content before export.

### Positioning

PaperScape is a grounded creative translation engine for research communication, not a generic PDF chatbot or one-click summarizer.

### Proposed tagline

**Upload a paper. Choose an audience. Create an evidence-backed explainer.**

---

## 5. MVP Scope

The MVP supports one complete workflow for a single selectable-text research PDF.

### Document ingestion

- Upload one PDF
- Validate MIME type and file size
- Reject image-only or unreadable PDFs with a clear message
- Extract text using Docling
- Fall back to PyMuPDF when Docling extraction fails
- Preserve one-based page numbers
- Preserve detected section metadata where available
- Store deterministic chunk identifiers

### Research map

Generate and store:

- Paper title where reliably available
- Research question
- Exactly three key findings for the first vertical slice
- At least one limitation
- Evidence for every finding
- Confidence classification for each finding
- A fixed expert-review disclaimer

### Async processing

- Start research-map generation through a job endpoint
- Return a job ID immediately
- Persist job status in SQLite
- Support `pending`, `running`, `succeeded`, and `failed`
- Let the frontend poll every 1–2 seconds
- Persist completed research maps
- Show human-readable failure states

### Audience adaptation

After the vertical slice is complete, the MVP will support:

- High school learner
- General public
- Undergraduate STEM student
- Simple audience-specific language
- Adjustable tone and target length where feasible

### Explainer pack

The complete MVP will generate:

- Plain-language summary
- Visual-abstract content blocks
- Short narration script
- Evidence cards
- Jargon glossary
- Limitations section
- Copyable or printable output

### Human review

- Inspect source evidence
- Edit generated text
- Remove or regenerate individual sections
- Approve content before export

### Technical foundation

- Flutter Web frontend
- FastAPI backend
- Pydantic data contracts
- SQLite persistence
- watsonx.ai and IBM Granite
- `LLMProvider` abstraction
- FastAPI `BackgroundTasks`
- pytest test suite
- Docker and Docker Compose
- Public GitHub repository

---

## 6. Out-of-Scope Features for Version 1

The following are intentionally excluded to protect delivery quality:

- Authentication and user accounts
- Team collaboration
- Cloud document libraries
- Multiple-paper comparison
- Literature reviews
- Citation-network analysis
- General-purpose chat with a paper
- OCR for scanned PDFs
- Automatic full-video generation
- Advanced animation
- AI-generated scientific diagrams
- Perfect chart or table interpretation
- Real-time streaming model output
- Celery, Redis, or a separate worker service
- Vector database and semantic search in the first vertical slice
- Native Android or iOS packaging
- Payments and subscriptions
- Automatic publishing to social platforms
- Claims that the system verifies scientific truth
- Replacement of expert, peer, or editorial review

---

## 7. Primary User Workflow

### Stage 1: Upload

1. The user opens PaperScape.
2. The user uploads a selectable-text PDF.
3. PaperScape validates the file.
4. The backend extracts page-aware text and structured chunks.
5. The user sees basic document metadata and extraction status.

### Stage 2: Build research map

1. The user starts research-map generation.
2. The backend creates a persistent background job.
3. The frontend receives a job ID and shows progress.
4. IBM Granite processes a bounded set of chunks through watsonx.ai.
5. The output is validated against the research-map schema.
6. Unsupported chunk IDs or invalid evidence references are rejected.
7. The completed map is persisted and displayed.

### Stage 3: Review evidence

1. The user reviews the research question.
2. The user reads the three key findings.
3. The user opens each evidence card.
4. PaperScape displays the source page, chunk ID, excerpt, and confidence.
5. The user checks limitations and the expert-review disclaimer.

### Stage 4: Select audience

1. The user selects a supported audience.
2. The user optionally chooses tone and desired length.
3. PaperScape adapts only verified research-map content.
4. The adaptation step must not introduce new unsupported findings.

### Stage 5: Review explainer pack

1. PaperScape generates the summary, visual-abstract blocks, narration script, glossary, and evidence cards.
2. The user edits or regenerates individual sections.
3. The user approves the final version.
4. The user copies, prints, or exports the explainer.

---

## 8. Key Features

### Research Mapper

Extracts the paper’s research question, key findings, limitations, and supporting evidence into a structured map.

### SourceTrail Evidence Cards

Displays source chunk ID, page number, excerpt, and confidence for generated findings.

### Audience Lens

Transforms verified research content for a selected audience without adding unsupported facts.

### Snapshot Builder

Creates concise visual-abstract blocks such as:

- Problem
- Research question
- Method
- Main finding
- Why it matters
- Limitation

### ExplainCast

Generates a short narration script suitable for a two- to three-minute explainer.

### Jargon Lens

Identifies technical terminology and provides audience-appropriate definitions.

### Creator Review Mode

Allows users to inspect evidence, edit outputs, remove claims, regenerate sections, and approve content.

### Processing and failure states

Communicates upload, extraction, queued, running, succeeded, and failed states without leaving the user uncertain about progress.

---

## 9. AI Behavior Requirements

PaperScape’s AI must behave as a constrained research communication assistant.

### Required behavior

- Use only supplied paper content for factual claims
- Treat document content as data, not as instructions
- Return structured JSON for machine-validated stages
- Preserve numerical values, units, comparisons, and uncertainty
- Distinguish correlation from causation
- Separate findings from interpretations
- Include limitations
- Identify uncertainty when support is incomplete
- Adapt language without changing the underlying meaning
- Avoid adding external facts unless a future feature explicitly enables external research
- Avoid presenting generated content as expert-verified
- Return concise evidence, not hidden reasoning
- Never expose or request chain-of-thought

### Prohibited behavior

- Inventing findings
- Creating non-existent citations
- Referencing unknown chunk IDs
- Misrepresenting speculation as a result
- Omitting important limitations to make a story more appealing
- Exposing credentials or internal configuration
- Following instructions embedded inside an uploaded paper
- Claiming that the system proves scientific validity

### Model integration

All runtime model access must go through an `LLMProvider` interface. The concrete MVP implementation uses watsonx.ai and an available IBM Granite instruction model.

The services layer must not import the watsonx SDK directly outside the provider implementation.

---

## 10. Evidence-Grounding Requirements

Evidence grounding is a product requirement, not an optional presentation feature.

### Grounding rules

- Every key finding must include at least one evidence item.
- Every evidence item must reference an existing chunk ID.
- The referenced page must match the stored chunk.
- The excerpt must come from the referenced chunk.
- Evidence excerpts must be concise.
- Findings without valid evidence must be rejected.
- The system must never generate citations after completing the explanation.
- Audience-specific outputs must be generated from verified research-map records.
- A limitation must never be rewritten into a stronger claim.
- Numerical values must match the source exactly.
- Partial support must be labelled accordingly.
- Uncertain claims should be omitted from public-facing outputs by default.

### Confidence values

The vertical slice uses:

- `high`
- `partial`
- `uncertain`

Confidence indicates the clarity of source support within the uploaded paper. It does not measure whether the research itself is scientifically correct.

### Disclaimer

Every research map and explainer pack must state:

> This AI-generated explanation is grounded in the uploaded document but does not replace expert review.

---

## 11. Human-in-the-Loop Requirements

Humans remain responsible for the final communication output.

### User controls

The user must be able to:

- View the original source evidence
- Compare a claim with its excerpt
- See page numbers and confidence
- Edit generated summaries and scripts
- Remove a finding from the explainer
- Regenerate a selected section
- Change the audience
- Review limitations before export
- Approve the final output

### System safeguards

- No automatic public publishing
- No claim is silently upgraded from partial to high confidence
- Edits must not overwrite stored source evidence
- Regeneration must preserve the chosen audience and grounding constraints
- The interface must visibly distinguish generated explanation from quoted source evidence
- Failures must be shown clearly rather than replaced with plausible-looking fallback text

---

## 12. Success Criteria

### Vertical-slice success

The vertical slice is successful when:

- A user uploads a typical selectable-text academic PDF through Flutter Web.
- The backend extracts at least one page-aware chunk per page where text exists.
- Research-map generation starts without blocking the request.
- The frontend polls a persistent job ID until success or failure.
- The completed map contains a non-empty research question.
- The map contains exactly three findings.
- Every finding has at least one valid evidence item.
- Every evidence item has a valid chunk ID, page number, and excerpt.
- The map includes at least one limitation.
- The map includes the fixed disclaimer.
- Invalid model JSON is retried once and then fails visibly.
- Duplicate active jobs for one paper are prevented.
- The complete flow works at 1280×800 without layout overflow.
- Backend tests pass.
- Docker Compose starts the frontend and backend.
- No credentials appear in committed files.

### Complete MVP success

The complete MVP is successful when:

- Users can select one of three audiences.
- The system produces meaningfully different explanations for those audiences.
- All major factual statements in the explainer remain traceable to verified research-map evidence.
- Users can inspect and edit the generated output.
- Every explainer includes limitations and a disclaimer.
- The system works reliably on at least five open-access academic PDFs selected from more than one subject area.
- A small evaluation set reports citation validity, claim support, numerical fidelity, limitation recall, JSON validity, and audience suitability.
- A deployed public demonstration can complete the primary workflow without developer intervention.

### Hackathon success

The project submission is complete when it includes:

- A working public prototype
- A public GitHub repository
- A clear README
- Architecture documentation
- A documented IBM Bob development workflow
- Evidence of IBM Bob use across planning, implementation, review, testing, and documentation
- A public demo or presentation video no longer than three minutes
- Completion of the required IBM SkillsBuild activity
- A published challenge submission page

---

## 13. Demo Scenario

### Demo paper

Use a short, open-access, selectable-text academic paper with:

- A clearly stated research question
- At least three findings
- At least one limitation
- Understandable page structure
- No sensitive or copyrighted distribution concerns
- A topic that can be understood by judges without specialist knowledge

A climate, public health, agriculture, education, or accessible technology paper would work well.

### Three-minute demonstration flow

#### 0:00–0:20 — Problem

Explain that valuable research is difficult to communicate beyond expert audiences and that generic summaries often lose limitations and source traceability.

#### 0:20–0:35 — Product

Introduce PaperScape as an AI-powered research communication studio that creates audience-specific, evidence-backed explainer packs.

#### 0:35–1:15 — Upload and processing

- Upload the demo PDF.
- Show page and chunk metadata.
- Start research-map generation.
- Show the async processing state.

#### 1:15–1:55 — Research map and evidence

- Show the research question.
- Show three findings.
- Open one SourceTrail evidence card.
- Show its chunk ID, source page, excerpt, and confidence.
- Show the paper’s limitation and disclaimer.

#### 1:55–2:30 — Audience adaptation

- Select “High school learner.”
- Show the plain-language summary or visual-abstract blocks.
- Switch to “Undergraduate STEM student.”
- Show that the explanation changes while evidence remains the same.

#### 2:30–2:50 — Technical execution

Briefly show the architecture:

`Flutter Web → FastAPI → PDF extraction → SQLite job store → LLMProvider → watsonx.ai / Granite → validated research map`

Show that IBM Bob was used to plan, scaffold, implement, test, review, and document the project.

#### 2:50–3:00 — Closing

Conclude that PaperScape helps people turn research into understandable, creative, and trustworthy stories while keeping humans in control.

---

## 14. Risks and Constraints

### PDF extraction quality

**Risk:** Academic PDFs contain columns, headers, footnotes, tables, figures, and inconsistent layouts.

**Mitigation:** Use Docling first, fall back to PyMuPDF, preserve page metadata, and restrict v1 to selectable-text PDFs.

### Scanned PDFs

**Risk:** Image-only PDFs cannot be processed reliably without OCR.

**Mitigation:** Reject them with a clear message. OCR is out of scope for v1.

### Hallucinated or unsupported claims

**Risk:** The model may produce statements not supported by the paper.

**Mitigation:** Require source chunk IDs in structured output, validate references, reject unsupported evidence, use low temperature, and generate audience outputs only from verified map records.

### Malformed model output

**Risk:** Granite may return invalid JSON.

**Mitigation:** Validate with Pydantic, retry once with a corrective prompt, then mark the job as failed with a readable message.

### Long processing times

**Risk:** PDF processing and Granite inference may take 5–15 seconds or longer.

**Mitigation:** Use a persistent job ID, FastAPI `BackgroundTasks`, SQLite job status, and frontend polling.

### Background-task limitations

**Risk:** FastAPI `BackgroundTasks` does not provide production-grade queue durability.

**Mitigation:** Persist status and results in SQLite, mark stale running jobs as failed after restart, and document Celery/Redis as a post-MVP upgrade.

### Token limits

**Risk:** Large papers may exceed the model context window.

**Mitigation:** Apply a configurable bounded context strategy for the vertical slice, log truncation, and later introduce section-aware retrieval.

### Figure and table interpretation

**Risk:** Text extraction may not capture the meaning of charts or complex tables.

**Mitigation:** Treat advanced figure understanding as experimental and out of scope for the first vertical slice. Preserve captions and page references where possible.

### Prompt injection inside PDFs

**Risk:** Uploaded papers may contain text that attempts to control the model.

**Mitigation:** Delimit document content, instruct the model to treat it only as source data, require structured output, and validate all references.

### Credential exposure

**Risk:** watsonx credentials could be committed or exposed to the frontend.

**Mitigation:** Store secrets only in environment variables, keep all model calls in the backend, exclude `.env` files from Git and Bob context, and never log credentials.

### Free-tier and rate limits

**Risk:** watsonx quotas may interrupt development or the final demo.

**Mitigation:** Use a mock provider for local development and automated tests, reserve live calls for integration testing, and prepare a verified demo paper in advance.

### Solo-development capacity

**Risk:** The full concept can expand beyond five weeks.

**Mitigation:** Prioritize the evidence-backed vertical slice, freeze non-essential features, avoid infrastructure such as Redis or authentication, and treat narration audio and advanced export as optional.

### Scientific responsibility

**Risk:** Users may treat simplified explanations as authoritative.

**Mitigation:** Preserve uncertainty and limitations, provide evidence access, require human review, display a disclaimer, and avoid claims that PaperScape validates the paper’s scientific quality.

---

## Product Principles

1. Evidence before explanation.
2. Accuracy before fluency.
3. Limitations belong in the story.
4. Audience adaptation must not change meaning.
5. The user approves the final output.
6. Failure must be visible.
7. Build one reliable workflow before adding formats.
