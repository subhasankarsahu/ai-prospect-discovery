# AI Prospect Discovery — LLM Evaluation Framework

## 1. Overview and Architecture

This directory houses the independent evaluation framework and curated ground-truth datasets for evaluating Large Language Model (LLM) performance in the **AI Prospect Discovery API**.

The framework isolates LLM evaluation from production code and covers the two primary AI operations:
1. **Query Intent Extraction**: Translating search queries into structured `QueryIntent` instances (`is_prospect_query`, `interest`, `audience`, `location`, `target_type`).
2. **Candidate Relevance Classification**: Classifying whether search result candidates represent individual human persons matching the requested interest and geography.

```
evaluation/
    README.md                                 # Framework documentation (this file)

    datasets/
        intents/
            development.json                  # 10 development intent extraction queries
            test.json                         # 20 held-out test intent extraction queries

        candidates/
            development.json                  # 30 development candidate profiles
            test.json                         # 50 held-out test candidate profiles

    ground_truth/
        intents/
            annotation_guide.md               # Human annotation policy for intent extraction
        candidates/
            annotation_guide.md               # Human annotation policy for candidate relevance

    review/
        export_review.py                      # Export pending annotations to CSV & JSON for review
        apply_review.py                       # Ingest human approvals without overwriting machine suggestions
        pending_candidate_reviews.csv         # Review-friendly tabular candidate export
        pending_candidate_reviews.json        # Review-friendly JSON candidate export
        pending_intent_reviews.csv            # Review-friendly tabular intent export
        pending_intent_reviews.json           # Review-friendly JSON intent export

    providers/
        base.py                               # ModelProvider protocol & evaluation data structures
        gemini.py                             # Configurable Google Gemini evaluation adapter
        mock_provider.py                      # Deterministic offline mock provider

    metrics/
        statistical.py                        # Wilson score confidence intervals & sample size warnings
        intent_metrics.py                     # Intent extraction metrics & hallucination detection
        candidate_metrics.py                  # Candidate precision, recall, F1, & ambiguity stats

    runner/
        config.py                             # EvaluationConfig with $0 budget enforcement
        run_evaluation.py                     # Offline evaluation CLI and orchestrator

    reports/
        model_comparison_template.md          # 17-section Google model comparison report template

    metadata/
        curate_milestone2.py                  # Dataset extraction and manifest generator
        dataset_manifest.json                 # Machine-readable metadata and verification records
        sampling_report.md                    # Methodology report on 80-candidate sampling
```

---

## 2. Dataset Structure and Integrity

- **Intent Queries (30 total)**:
  - `development.json`: 10 queries (8 prospect, 2 non-prospect)
  - `test.json`: 20 queries (16 prospect, 4 non-prospect)
- **Candidate Profiles (80 total)**:
  - `development.json`: 30 candidate profiles
  - `test.json`: 50 candidate profiles
  - Sourced from 140 raw search results across 4 populated Phase 4 fixtures (`cricket_lovers_ahmedabad`, `digital_marketing_owners_new_york`, `football_lovers_washington_dc`, `startup_founders_london`).
  - Represents 7 platforms (LinkedIn, X, YouTube, Instagram, Threads, Facebook, and Web).

---

## 3. Human Review Workflow

All 110 dataset records are initially marked with `status: "needs_human_review"`. To finalize ground truth:

1. **Inspect Pending Reviews**:
   - Tabular view: Open `evaluation/review/pending_candidate_reviews.csv` or `pending_intent_reviews.csv` in Excel or any CSV editor.
   - Structured view: Open `evaluation/review/pending_candidate_reviews.json` or `pending_intent_reviews.json`.
2. **Reviewing Candidates**:
   - Each entry displays the original `title`, `snippet`, and machine suggestions.
   - Set `decision_status` to `"reviewed"` (or `"rejected"`).
   - Enter `approved_overall` (`positive`, `negative`, or `ambiguous`), `reviewer_name`, and `review_notes`.
3. **Applying Approvals**:
   - Run:
     ```bash
     python evaluation/review/apply_review.py
     ```
   - Ingestion updates the dataset records while **strictly preserving** original machine suggestions in `machine_suggestion` and `machine_evidence` fields.

---

## 4. Annotation Policy & Ambiguity Rules

### Candidate Ambiguity Policy
**Mandatory rule: Ambiguous examples are NEVER classified as negative ground truth.**
- **Primary Binary Metrics (Precision, Recall, F1)** are computed exclusively on confirmed human-reviewed **positive** and **negative** examples.
- Ambiguous candidates are tracked separately in an **Uncertainty Report** (count, percentage, model acceptance rate, model low-confidence rate).
- Unreviewed records (`status: "needs_human_review"`) are strictly excluded from primary benchmark scores.

### Intent Annotation Policy
- Evaluates on `QueryIntent` fields (`is_prospect_query`, `interest`, `audience`, `location`, `target_type`).
- Evaluates acceptable semantic variants (exact string equality is not required for valid synonyms).
- Penalizes hallucinated conversational commentary in geographic fields (as observed in baseline Gemini).

---

## 5. Offline Execution and $0 Budget Protection

### Why Live Inference Is Disabled
This project operates under a strict **$0.00 budget**. No live requests to Gemini, Tavily, or any other external API are permitted without explicit written authorization.

- `EvaluationConfig` enforces `budget_cap_usd = 0.0`.
- `GeminiEvaluationProvider` raises `ZeroBudgetViolationError` if any live network call is attempted under a zero budget.
- The evaluation runner executes **100% offline** by default using mock test doubles.

### How to Run Offline Evaluation
To execute an offline evaluation run with mock test doubles:

```bash
python -m evaluation.runner.run_evaluation
```

This generates an evaluation report JSON in `evaluation/reports/`.

---

## 6. Protection of the Held-Out Test Set

To prevent benchmark data leakage:
- By default, `EvaluationConfig.split` is set to `"development"`.
- The held-out `test.json` split (20 intents, 50 candidates) must **never** be used for prompt engineering, few-shot selection, or hyperparameter tuning.
- It is reserved exclusively for final, one-pass model comparisons.

---

## 7. Configuring Model Identifiers for Future Comparisons

When live model comparisons are authorized in the future:
1. Configure model IDs via environment variables or `EvaluationConfig`:
   - `model_id`: e.g., `"gemini-3.5-flash-lite"`
   - `alternative_model_id`: e.g., `"gemini-2.5-flash"` or a verified Google alternative.
2. Only Google Gemini models are permitted. No OpenAI or third-party providers are supported.
3. Compare models using identical input datasets, fixed prompts, and the report template in `evaluation/reports/model_comparison_template.md`.
