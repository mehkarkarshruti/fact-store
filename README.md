# FactStore — A Fact Knowledge Layer for PDFs

FactStore reads PDFs, extracts grounded factual claims, links each fact to the exact
page and quote it came from, and reconciles facts across documents — flagging when
they corroborate, contradict, or are reconciled by context (time, scope, or units).


---

## Setup and Run Instructions

**Requirements:** Python 3.10+, a free [Gemini API key](https://aistudio.google.com/apikey)

```bash
git clone https://github.com/mehkarkarshruti/fact-store.git
pip install -r requirements.txt

cp .env.example .env
# open .env and paste your GEMINI_API_KEY

streamlit run app/ui.py
```

The app opens with **pre-computed sample results already loaded and browsable** —
no API key is required just to explore the Delhivery and India-macroeconomy
datasets under "Overview / casebook" and "Audit findings."

An API key is only needed if you want to process a **new** PDF yourself via the
"Ingest & reconcile" tab, since that triggers live extraction calls to Gemini.

### Project structure

```
app/
├── ui.py          # Streamlit UI (three tabs: casebook, findings, ingest)
├── extract.py     # PDF → chunked text → LLM → structured Fact objects
├── compare.py     # Cross-document reconciliation (corroborate/contradict/context)
├── pdf_reader.py  # PyMuPDF text extraction + chunking with page tags
├── schema.py      # Pydantic schema for Fact / FactList
└── prompts.py     # Extraction prompt template

db/
├── facts/              # Raw per-document extracted facts (pre-comparison)
│   ├── delhivery/       # sample: Delhivery prospectus, annual report, earnings deck
│   ├── macro/            # sample: Economic Survey, RBI Annual Report, IMF report
│   └── uploads/            # auto-populated when a PDF is uploaded via the UI
└── reconciliations/     # Cross-document comparison output
    ├── delhivery/
    ├── macro/
    └── uploads/            # auto-populated after live ingestion
```

---

## Video Demo

[**Watch the demo**](<https://drive.google.com/file/d/1aRPJVZ_BoJvI8InS9PBBWgWLfM07M-KXn/view?usp=sharing>)

The video walks through:
1. A fact corroborated across two Delhivery documents (revenue, stated differently)
2. A genuine contradiction between the Economic Survey and RBI Annual Report on 2024 global growth
3. An apparent contradiction resolved by context (EBITDA trajectory across time periods)
4. A live PDF upload, showing extraction and reconciliation running end-to-end
5. A known extraction/reasoning failure and how it would be fixed

---

## Approach

### Pipeline

1. **Extraction** (`extract.py`) — Each PDF is read with PyMuPDF, chunked by page
   ranges (default: 3 pages per chunk) so extraction stays within LLM output-token
   limits on long documents. Each chunk is tagged with `[PAGE N]` markers and sent
   to **Gemini** with a strict JSON schema (via Pydantic `response_schema`), so the
   model can only return valid, structured `Fact` objects — never freeform prose.
   Facts include `subject`, `predicate`, `value`, `unit`, `time_period`, and a
   mandatory `evidence_text`: an exact verbatim quote from the source, which is the
   main defense against hallucination — a fact without a real supporting quote is
   never trusted as fully grounded.

2. **Grounding** — Every fact carries its source filename and page number,
   assigned deterministically by our own code after parsing (not by the LLM), so
   fact IDs and page attributions stay consistent and collision-free across chunks
   and documents.

3. **Reconciliation** (`compare.py`) — Facts from multiple documents are pooled and
   sent to Gemini, which groups them into unified metric tracks and classifies each
   as `CORROBORATED`, `CONTRADICTION`, `CONSISTENT_TIMELINE` (context resolves an
   apparent mismatch), or `UNRECONCILED`. Each verdict includes a synthesis
   explaining the reasoning and links back to every supporting evidence point.

4. **Interface** (`ui.py`) — A Streamlit app with three views: a guided casebook
   showing one example of each required case, a searchable/filterable findings
   explorer, and a live ingestion tab that runs the full pipeline on newly
   uploaded PDFs and writes results into their own store, separate from the
   curated sample data.

### Key design decisions

- **No hard-coded facts, filenames, or schemas.** The extraction prompt asks the
  LLM to find whatever factual claims exist in the text — it isn't told to look
  for specific fields like "revenue" or "GDP." This is what lets the same pipeline
  run unmodified on documents it has never seen.
- **Structured output over regex parsing.** Forcing the LLM into a JSON schema
  instead of parsing free text avoids a large, fragile class of parsing bugs.
- **Chunking by page range, not whole-document.** 90–100 page source PDFs exceed
  what a single LLM call can reliably extract facts from without truncation, so
  documents are processed in page-range chunks with page markers preserved for
  grounding.
- **Raw facts and reconciliation output are stored separately** (`db/facts/` vs
  `db/reconciliations/`), so the UI can never accidentally treat an unprocessed
  fact file as a finished "finding."
- **Comparison is done in a single pooled LLM call per document set** rather than
  a pairwise embedding-similarity search. This is a deliberate simplification
  given the scale of three sample documents; see Limitations for how this would
  need to change at larger scale.

### AI tools used

- **Google Gemini** (free tier) for both fact extraction and cross-document
  reconciliation, via structured JSON output.
- **Manus AI** for ui fixes and refactoring.

---

## Limitations and Next Steps

**What doesn't work yet:**

- **Silent extraction failures under rate limits.** Running on Gemini's free tier,
  a small number of chunks occasionally failed extraction under rate limiting and
  returned zero facts instead of raising a visible error. This means some source
  pages could be under-represented in the knowledge layer without any obvious
  signal to the user. This is the "reasoning/extraction failure" case shown in
  the demo video.
- **Latency.** Processing a document end-to-end (chunking → per-chunk extraction
  calls → reconciliation) takes noticeably longer than a user would want in an
  interactive tool, since each chunk is a separate sequential LLM call with a
  deliberate delay between calls to stay under free-tier rate limits. A 100-page
  document can take several minutes to fully process. This would need parallel
  chunk processing (with proper rate-limit-aware batching) and/or a paid tier
  with higher throughput to feel responsive at scale.
- **Facts that span a chunk boundary can be lost or split.** Since documents are
  split into fixed page-range chunks before extraction, a fact whose supporting
  context is spread across the end of one chunk and the start of the next (e.g. a
  claim introduced on one page and only fully quantified a page later, or a table
  that continues across a chunk boundary) may be extracted incompletely, missed
  entirely, or extracted twice with slightly different wording in each chunk. No
  overlap window or cross-chunk stitching is currently implemented.
- **Facts inside charts, graphs, and images are not extracted.** Extraction relies
  on `PyMuPDF`'s text layer only, so any fact that exists purely as a visual
  element — a bar chart value, a trend line, an infographic number rendered as an
  image rather than text — is invisible to the pipeline. Several of the source
  PDFs (especially the earnings presentation) contain exactly this kind of visual
  data, some of which is likely missed as a result.
- **Comparison does not scale past a handful of documents.** `compare.py`
  currently sends the entire pooled fact set from all documents to the LLM in one
  call. This works at the scale of the starter datasets (a few hundred facts) but
  would hit token/output limits with many more documents or much larger fact
  counts.
- **No incremental updates.** Adding a new document currently means re-running
  reconciliation across the full pool of facts rather than only comparing the new
  facts against existing ones.
- **No entity resolution beyond what the LLM infers in-context.** Matching that
  "the Company" in one document and "Delhivery Limited" in another refer to the
  same entity relies entirely on the LLM's reasoning within a single reconciliation
  call, with no separate canonicalization step.

**What I'd build next, given more time:**

1. Add an embedding-based candidate filter (sentence-transformers + cosine
   similarity) before the LLM comparison step, so only likely-related fact pairs
   are sent for expensive reasoning — this both reduces token usage and would let
   reconciliation scale to many more documents.
2. Surface failed-chunk warnings directly in the UI, with a visible retry queue,
   instead of silently returning zero facts.
3. Add a small page-overlap window between consecutive chunks (e.g. repeating the
   last paragraph of chunk N at the start of chunk N+1) so facts spanning a chunk
   boundary are less likely to be lost or duplicated, plus a de-duplication pass
   on the resulting facts.
4. Extract chart/table images per page (via PyMuPDF's image and table detection)
   and run them through a vision-capable pass so facts that only exist visually
   are no longer invisible to the system.
5. Parallelize chunk-level extraction calls (with rate-limit-aware batching) to
   reduce end-to-end latency on longer documents.
6. Support incremental ingestion: compare only new facts against the existing
   fact store, rather than rebuilding all reconciliations from scratch.
7. Add a lightweight entity-resolution/canonicalization pass so the same
   real-world entity is recognized consistently across differently-worded
   references.

---

## Additional Notes

- Sample outputs for both starter datasets (Delhivery and India macroeconomy) are
  committed under `db/facts/` and `db/reconciliations/`, so the four required
  cases are fully browsable without needing to run extraction or supply an API
  key.
- The demo video shows a live extraction + reconciliation run on camera using the
  starter dataset PDFs uploaded through the app itself, to demonstrate the full
  pipeline working end-to-end.