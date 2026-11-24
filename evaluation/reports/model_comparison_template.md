# Google Gemini LLM Model Comparison Report Template

**Document Status:** TEMPLATE / OFFLINE PREPARATION ONLY  
**Evaluation Mode:** STRICTLY OFFLINE (Mock Test Doubles / Zero API Calls)  
**Permitted Provider:** Google Gemini Models Only  
**API Budget Spent:** $0.00  

---

## 1. Executive Summary

| Evaluation Attribute | Production Baseline Model | Alternative Candidate Model |
|---|---|---|
| **Model Identifier** | `gemini-3.5-flash-lite` | `[VERIFIED_GOOGLE_ALTERNATIVE_MODEL]` |
| **API Provider** | Google (Generative Language API) | Google (Generative Language API) |
| **Execution Status** | **OFFLINE TEST ONLY / NOT RUN LIVE** | **NOT RUN LIVE** |
| **Primary Evaluation Recommendation** | Pending Human Ground-Truth Review | Pending Verification & Approval |

---

## 2. Model Identifiers and Configuration

| Parameter | Baseline Model | Alternative Model |
|---|---|---|
| **Model ID** | `gemini-3.5-flash-lite` | `[TO_BE_VERIFIED]` |
| **API Endpoint** | `generativelanguage.googleapis.com` | `generativelanguage.googleapis.com` |
| **Structured Output Format** | Native `responseSchema` (JSON) | Native `responseSchema` (JSON) |
| **Temperature** | `0.0` (deterministic) | `0.0` (deterministic) |
| **API Budget Cap** | **$0.00** | **$0.00** |

---

## 3. Dataset Versions and Provenance

- **Evaluation Dataset Version**: `ai-prospect-discovery-eval-v1`
- **Total Intent Queries Prepared**: 30 queries (10 Development, 20 Held-Out Test)
- **Total Candidate Profiles Prepared**: 80 candidates (30 Development, 50 Held-Out Test)
- **Source Fixtures**: `cricket_lovers_ahmedabad.json`, `digital_marketing_owners_new_york.json`, `football_lovers_washington_dc.json`, `startup_founders_london.json`
- **Tavily Search Requirement**: 0 search calls (Offline static snippets only).

---

## 4. Ground-Truth Review Status

- **Candidate Annotations Awaiting Human Approval**: 80 (`status: "needs_human_review"`)
- **Intent Annotations Awaiting Human Approval**: 30 (`status: "needs_human_review"`)
- **Confirmed Human-Approved Labels**: 0
- *Notice: Primary benchmark metrics must not be treated as final until ground truth is reviewed by the project owner.*

---

## 5. Intent Extraction Performance Comparison

| Metric | Baseline: `gemini-3.5-flash-lite` | Alternative Model | Performance Delta |
|---|:---:|:---:|:---:|
| **Prospect Detection Accuracy** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Prospect Detection Precision** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Prospect Detection Recall** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Prospect Detection F1** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Interest Semantic Accuracy** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Location Normalization Accuracy** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Structured JSON Validity Rate** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Hallucination / Prose Rate** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |

---

## 6. Candidate Classification Performance Comparison

*(Evaluated on human-reviewed positive and negative candidates; ambiguous candidates strictly excluded from primary binary scores)*

| Metric | Baseline: `gemini-3.5-flash-lite` | Alternative Model | Performance Delta |
|---|:---:|:---:|:---:|
| **Model-Level Precision** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Model-Level Recall** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Model-Level F1 Score** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Pipeline-Level Precision** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Pipeline-Level Recall** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Pipeline-Level F1 Score** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Individual Person Accuracy** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Name Support Accuracy** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Interest Support Accuracy** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |
| **Location Support Accuracy** | `NOT RUN LIVE` | `NOT RUN LIVE` | — |

---

## 7. Ambiguous Candidate Behavior & Uncertainty Statistics

| Ambiguity Metric | Baseline Model | Alternative Model |
|---|:---:|:---:|
| **Total Ambiguous Ground-Truth Profiles** | 1 (1.25% of dataset) | 1 (1.25% of dataset) |
| **Ambiguous Candidates Accepted by Model** | `NOT RUN LIVE` | `NOT RUN LIVE` |
| **Ambiguous Candidates Rejected by Model** | `NOT RUN LIVE` | `NOT RUN LIVE` |
| **Model Low-Confidence Predictions** | `NOT RUN LIVE` | `NOT RUN LIVE` |

---

## 8. False-Positive and False-Negative Error Analysis

- **False-Positive Analysis**: `NOT AVAILABLE` (Requires live inference run).
- **False-Negative Analysis**: `NOT AVAILABLE` (Requires live inference run).

---

## 9. Model-Level vs. Pipeline-Level Breakdown

- **Model vs Filter Discrepancies**: Evaluates whether candidates rejected by the pipeline failed due to LLM person/interest classification or downstream deterministic verbatim name checking. `NOT RUN LIVE`.

---

## 10. Structured Response Validity

| Validation Metric | Baseline Model | Alternative Model |
|---|:---:|:---:|
| **JSON Schema Adherence** | `NOT RUN LIVE` | `NOT RUN LIVE` |
| **Malformed JSON Occurrences** | `NOT RUN LIVE` | `NOT RUN LIVE` |
| **Missing Required Fields** | `NOT RUN LIVE` | `NOT RUN LIVE` |

---

## 11. Latency Profile

| Latency Metric | Baseline Model | Alternative Model |
|---|:---:|:---:|
| **Intent Extraction Mean Latency** | `NOT RUN LIVE` | `NOT RUN LIVE` |
| **Intent Extraction Median (P50)** | `NOT RUN LIVE` | `NOT RUN LIVE` |
| **Candidate Batch Mean Latency** | `NOT RUN LIVE` | `NOT RUN LIVE` |
| **Candidate Batch Median (P50)** | `NOT RUN LIVE` | `NOT RUN LIVE` |

---

## 12. Token Consumption

| Token Metric | Baseline Model | Alternative Model |
|---|:---:|:---:|
| **Average Prompt Tokens / Query** | `NOT RUN LIVE` | `NOT RUN LIVE` |
| **Average Output Tokens / Query** | `NOT RUN LIVE` | `NOT RUN LIVE` |
| **Average Prompt Tokens / Batch** | `NOT RUN LIVE` | `NOT RUN LIVE` |
| **Average Output Tokens / Batch** | `NOT RUN LIVE` | `NOT RUN LIVE` |

---

## 13. Cost Estimation

| Pricing Metric | Baseline Model | Alternative Model |
|---|:---:|:---:|
| **Input Price / 1M Tokens** | `MANUALLY_CONFIGURED` | `MANUALLY_CONFIGURED` |
| **Output Price / 1M Tokens** | `MANUALLY_CONFIGURED` | `MANUALLY_CONFIGURED` |
| **Estimated Cost / 1k Searches** | `NOT ESTIMATED` | `NOT ESTIMATED` |
| **Actual Evaluation Spend** | **$0.00** | **$0.00** |

---

## 14. Operational Reliability and Error Handling

| Reliability Indicator | Baseline Model | Alternative Model |
|---|:---:|:---:|
| **First-Attempt Success Rate** | `NOT RUN LIVE` | `NOT RUN LIVE` |
| **Rate Limit (429) Encounters** | `NOT RUN LIVE` | `NOT RUN LIVE` |
| **Timeout (504) Encounters** | `NOT RUN LIVE` | `NOT RUN LIVE` |

---

## 15. Qualitative Failure Examples

- Examples will be cataloged when authorized live inference is executed.

---

## 16. Statistical Limitations and Sample Warnings

- **Intent Sample Size**: $N = 30$ ($N = 10$ Dev, $N = 20$ Test). Confidence intervals for sub-groups are wide.
- **Candidate Sample Size**: $N = 80$ ($N = 30$ Dev, $N = 50$ Test).
- **Domain Coverage**: Sourced from Phase 4 recorded domains (cricket, digital marketing, football, London startups).

---

## 17. Final Engineering Recommendation

- **Verdict**: `PENDING GROUND-TRUTH REVIEW & LIVE BENCHMARK EXECUTION`
- *No model replacement may be recommended until human ground truth is approved and live benchmark metrics are empirically observed under authorized budget.*
