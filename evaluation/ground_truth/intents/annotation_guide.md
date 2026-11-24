# Query Intent Extraction — Annotation Guide

## 1. Purpose

This document defines the formal ground-truth annotation policy for evaluating the **Query Intent Extraction** component of the AI Prospect Discovery API.

The evaluation dataset comprises **30 intent queries** partitioned into:
- **Development Set**: 10 queries (`evaluation/datasets/intents/development.json`)
- **Held-Out Test Set**: 20 queries (`evaluation/datasets/intents/test.json`)

---

## 2. Intent Schema Definitions

Every intent record evaluates against the application's core `QueryIntent` schema:

| Field Name | Type | Description | Mandatory in Ground Truth |
|---|---|---|:---:|
| `is_prospect_query` | `boolean` | Whether the query seeks to discover candidate people or organizations. | Yes |
| `interest` | `string` | Primary industry, skill, domain, or role of interest. | Yes |
| `audience` | `string \| null` | Target market persona or sub-group if specified. | Yes |
| `location.city` | `string \| null` | Canonical city name. | No (null if unspecified) |
| `location.state` | `string \| null` | Canonical state or province name. | No (null if unspecified) |
| `location.country` | `string \| null` | Canonical country name. | No (null if unspecified) |
| `target_type` | `string` | Target entity category (e.g., `"individual"`, `"founder"`, `"agency owner"`). | Yes |

*Note: The application does NOT extract `platform` from query text; searches are uniformly dispatched across all supported platforms. Platform extraction accuracy is intentionally excluded.*

---

## 3. Labeling Rules & Guidelines

### A. Prospect Query Classification (`is_prospect_query`)
- **Set to `true`** if the query is seeking to discover, find, recruit, or contact individual humans, founders, professionals, or organizations.
  - *Examples*: `"Startup founders in London"`, `"Python engineers in Berlin"`, `"Software companies in Dublin"`.
- **Set to `false`** if the query is a general knowledge question, technical programming instruction, weather lookup, financial quote, or consumer place recommendation.
  - *Examples*: `"What is the capital of France?"`, `"How to configure FastAPI with async HTTPX?"`, `"Weather forecast for Seattle"`, `"Best pizza restaurants near Central Park"`.

### B. Interest Extraction (`interest`)
- Must reflect the core domain or activity without extraneous conversational fluff.
- Strip search prefixes such as `"Find..."`, `"Looking for..."`, or `"Who are..."`.
- *Example*: For query `"Looking for renewable energy project managers in Oslo Norway"`, canonical interest is `"renewable energy"`.

### C. Geographic Constraints (`location`)
- **City, State, Country**: Record canonical clean strings.
- **Strict Prohibition Against Verbose Hallucination**:
  - The model must output concise geographic names (e.g., `city: "New York"`, `state: "NY"`, `country: "USA"`).
  - Any model output inserting conversational meta-reasoning (e.g. `"New York State or NY implied context not explicitly separated..."`) must be evaluated as an extraction defect.
- **Missing Locations**:
  - If no location is mentioned (e.g., `"Graphic designers specializing in brand identity"`), `location` must be `null`.
  - The model must not hallucinate a location when none is present.

### D. Target Entity Type (`target_type`)
- Must capture the entity persona: e.g., `"founder"`, `"engineer"`, `"agency owner"`, `"individual"`, `"company"`.

### E. Acceptable Semantic Variants (`acceptable_variants`)
- Exact string matches are rarely realistic in natural language processing.
- The ground truth defines `acceptable_variants` for `interest`, `audience`, `location`, and `target_type`.
- A prediction matching any listed acceptable variant is scored as correct.

---

## 4. Human Review Workflow

1. Open `evaluation/datasets/intents/development.json` or `test.json`.
2. Review the `ground_truth` and `acceptable_variants` against `input_query`.
3. If the annotation is accurate, update:
   ```json
   "annotation": {
     "status": "reviewed",
     "labeler": "<your_name_or_initials>",
     "reviewed_at": "YYYY-MM-DD",
     "notes": "Verified canonical intent."
   }
   ```
4. If an annotation requires alteration, edit the expected values and set `status: "reviewed"`.
5. If an example is invalid or irrecoverably flawed, set `status: "rejected"`.
