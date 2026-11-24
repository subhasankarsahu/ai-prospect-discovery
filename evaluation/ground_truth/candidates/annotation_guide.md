# Candidate Relevance Classification — Annotation Guide

## 1. Purpose

This document defines the formal ground-truth annotation policy for evaluating the **Candidate Relevance Classification** component of the AI Prospect Discovery API.

The evaluation dataset comprises **80 candidate examples** partitioned into:
- **Development Set**: 30 candidates (`evaluation/datasets/candidates/development.json`)
- **Held-Out Test Set**: 50 candidates (`evaluation/datasets/candidates/test.json`)

---

## 2. Candidate Annotation Schema

Each candidate record contains the original search result input, independent ground-truth labels across five dimensions, traceable evidence excerpts, and human review metadata:

```json
{
  "example_id": "cand_001",
  "source_fixture": "startup_founders_london",
  "source_query": "Startup founders in London UK",
  "platform": "LinkedIn",
  "input": {
    "title": "John-Pierre Clark - Editor & Founder - London | LinkedIn",
    "snippet": "London, UK · Editor & Founder · Clark Media. London startup ecosystem..."
  },
  "ground_truth": {
    "is_individual_person": "positive",
    "name_supported": "positive",
    "interest_supported": "positive",
    "location_supported": "positive",
    "overall_acceptability": "positive"
  },
  "evidence": {
    "name": "John-Pierre Clark",
    "interest": "Founder",
    "location": "London"
  },
  "annotation": {
    "status": "needs_human_review",
    "labeler": null,
    "reviewed_at": null,
    "notes": "Individual founder based in London."
  }
}
```

---

## 3. Ground-Truth Dimension Definitions

For each dimension, assign one of three allowed ternary values:
- `"positive"`: Clear, verifiable evidence in the input title or snippet supports the condition.
- `"negative"`: Evidence contradicts the condition or evidence is clearly absent.
- `"ambiguous"`: Evidence is mixed, vague, or insufficient to reach a definitive conclusion.

### A. Individual Person (`is_individual_person`)
- **Positive**: The profile represents a living human individual (e.g. personal LinkedIn profile, personal Threads/X account, named founder/executive).
- **Negative**:
  - Corporate / Company Pages: `Cherry Ventures`, `Star Tech SEO`, `Rare Founders`.
  - Sports Teams & Franchises: `Washington Commanders`, `Gujarat Titans`.
  - Leagues & Venues: `Abcl Ahmedabad Box Cricket League`, `Audi Field`.
  - Generic Landing Pages / Articles: `12 Best SEO Agencies`, `Upcoming Cricket Events`.
- **Ambiguous**: Snippet text is ambiguous between an individual consultant and an agency (e.g., `"PlayBook Membership | Branding & Marketing Agency"`).

### B. Name Support (`name_supported`)
- **Positive**: A recognizable person or entity name appears explicitly in the title or snippet.
- **Negative**: No identifiable name is present in the text (e.g. `"How To Start A Digital Marketing Agency"`).
- **Verbatim Substring Rule**: For positive name support, the exact name excerpt MUST exist verbatim in the title or snippet.

### C. Interest Support (`interest_supported`)
- **Positive**: Direct textual evidence in the snippet or title connects the candidate to the target query interest (e.g. `"SEO"`, `"founder"`, `"cricket"`, `"football"`).
- **Negative**: The candidate text contains no mention or connection to the requested interest.
- **Ambiguous**: The candidate operates in a vaguely related or tangential domain without explicit support.

### D. Location Support (`location_supported`)
- **Positive**: Direct textual evidence confirms the requested city, state, or country (e.g. `"London"`, `"New York"`, `"Ahmedabad"`, `"Washington DC"`).
- **Negative**: The candidate is explicitly located elsewhere (e.g. a London query returning a candidate located in New Zealand).
- **Ambiguous**: No geographic location is mentioned in the text.

### E. Overall Acceptability (`overall_acceptability`)
Reflects the end-to-end prospect discovery standard:
- **Positive**: The candidate satisfies all prospect discovery requirements:
  - `is_individual_person` == "positive"
  - `name_supported` == "positive" (verbatim name match in title or snippet)
  - `interest_supported` == "positive" (direct evidence in title or snippet)
  - `location_supported` == "positive" (direct evidence in title or snippet)
- **Negative**: The candidate clearly fails at least one required criterion (e.g., corporate page, unrelated domain, conflicting location, or non-profile web page).
- **Ambiguous**: Evidence is borderline, incomplete, or partially conflicting across dimensions, with none definitively negative.

---

## 4. Critical Policy on Ambiguous Examples

**Mandatory Rule: Do NOT classify ambiguous examples as negative ground truth!**

In evaluation:
1. **Primary Binary Metrics (Precision, Recall, F1, False Positive Rate, False Negative Rate)**:
   - Evaluated strictly on confirmed, human-reviewed **positive** and **negative** examples.
   - Ambiguous examples are **strictly excluded** from the denominator and numerator of binary precision, recall, and F1 calculations.
   - Number and percentage of ambiguous candidates are reported separately.
2. **Dedicated Uncertainty Metric**:
   - Measured independently:
     - **Ambiguous Acceptance Rate**: How often the model accepts a ground-truth ambiguous candidate.
     - **Ambiguous Rejection Rate**: How often the model rejects a ground-truth ambiguous candidate.
     - **Model Uncertainty Expression**: How often the model outputs `"confidence": "low"` on ambiguous profiles.
3. **Unreviewed Example Exclusion**:
   - Unreviewed examples (`status: "needs_human_review"`) must **never** silently enter primary test metrics. They must be reported as pending human review.

---

## 5. Evidence Traceability Rule

For any positive dimension:
- The corresponding `evidence` field (`name`, `interest`, or `location`) must contain a string excerpt copied **verbatim** from `input.title` or `input.snippet`.
- If a dimension is `negative`, its evidence field must be an empty string `""`.
- Automated validation tests enforce that every non-empty evidence string is a case-sensitive or case-insensitive substring of the input.

---

## 5. Human Review Workflow

1. Open `evaluation/datasets/candidates/development.json` or `test.json`.
2. Inspect the candidate's `input.title` and `input.snippet`.
3. Verify that `ground_truth` and `evidence` accurately reflect the source text.
4. Update the annotation record:
   ```json
   "annotation": {
     "status": "reviewed",
     "labeler": "<your_name_or_initials>",
     "reviewed_at": "YYYY-MM-DD",
     "notes": "Verified individual prospect."
   }
   ```
5. Do not modify the original `input.title` or `input.snippet` text.
