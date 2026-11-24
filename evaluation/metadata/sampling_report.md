# Candidate Sampling and Dataset Distribution Report

## 1. Executive Summary

This report documents the sampling methodology, platform distribution, and development/test split strategy used to curate the 80 candidate classification evaluation examples from the 140 raw search results across the four populated Phase 4 fixtures in `tests/fixtures/`.

---

## 2. Source Fixtures and Candidate Population

The Phase 4 test fixtures contain raw search results retrieved via Tavily across 7 distinct platform search queries (LinkedIn, X, YouTube, Instagram, Threads, Facebook, and Google unrestricted search).

| Fixture File | Search Calls | Raw Search Candidates | Profile URLs Discovered | Non-Profile Search Results | Selected Evaluation Sample |
|---|:---:|:---:|:---:|:---:|:---:|
| `cricket_lovers_ahmedabad.json` | 7 | 35 | 6 | 29 | **20** |
| `digital_marketing_owners_new_york.json` | 7 | 35 | 15 | 20 | **20** |
| `football_lovers_washington_dc.json` | 7 | 35 | 13 | 22 | **20** |
| `startup_founders_london.json` | 7 | 35 | 13 | 22 | **20** |
| `restaurant_owners_dubai.json` | 0 | 0 | 0 | 0 | **0 (Excluded)** |
| **Total** | **28** | **140** | **47** | **93** | **80** |

*Note: `restaurant_owners_dubai.json` was an empty recording fixture from Phase 4 and is strictly excluded from candidate evaluation.*

---

## 3. Sampling Methodology

To ensure an unbiased and comprehensive evaluation dataset:

1. **Equal Representation Across Fixtures**: Exactly 20 candidates are selected from each of the 4 populated fixtures ($20 \times 4 = 80$).
2. **Inclusion of All Discovered Profile Candidates**: All 47 unique profile candidates (including the 45 candidates that reached Gemini in Phase 4) are retained in the evaluation set to benchmark model agreement and error rates.
3. **Inclusion of Non-Profile Candidates (Negative Controls)**: 33 non-profile search results (organizations, venues, directories, Wikipedia entries, media articles) are sampled to test the model's ability to reject non-individuals and non-profile pages.
4. **Reproducible Extraction**: Sampling is executed deterministically by `curate_milestone2.py` without random jitter or dynamic network calls.

---

## 4. Platform Distribution of the Selected Sample

The 80 candidate examples span across all target discovery platforms and external web sources:

| Platform | Candidate Count | Percentage | Profile URLs | Non-Profile Web Pages |
|---|:---:|:---:|:---:|:---:|
| **LinkedIn** | 18 | 22.5% | 12 | 6 (Articles, jobs, company pages) |
| **X (Twitter)** | 16 | 20.0% | 11 | 5 (News posts, media handles) |
| **YouTube** | 12 | 15.0% | 4 | 8 (Game highlights, how-to tutorials) |
| **Instagram** | 11 | 13.75% | 7 | 4 (Event reels, stadium photos) |
| **Threads** | 10 | 12.5% | 8 | 2 (Community threads, news updates) |
| **Facebook** | 9 | 11.25% | 5 | 4 (Groups, event listings, venues) |
| **Web / Google** | 4 | 5.0% | 0 | 4 (Ticketing, Wikipedia, directories) |
| **Total** | **80** | **100%** | **47** | **33** |

---

## 5. Development and Held-Out Test Split

The 80 candidates are partitioned into:
- **Development Set**: 30 candidates (37.5%)
- **Held-Out Test Set**: 50 candidates (62.5%)

### Partition Strategy by Fixture
To prevent query-domain skew while keeping near-duplicates in the same split:
- `cricket_lovers_ahmedabad`: 8 Dev, 12 Test (Total 20)
- `digital_marketing_owners_new_york`: 7 Dev, 13 Test (Total 20)
- `football_lovers_washington_dc`: 8 Dev, 12 Test (Total 20)
- `startup_founders_london`: 7 Dev, 13 Test (Total 20)

**Zero-Leakage Assurance**: Each example carries a stable unique identifier (`cand_001` through `cand_080`). No identifier or candidate record is shared across the development and test datasets.

---

## 6. Ground-Truth Distribution Summary (Preliminary)

Prior to human review, the preliminary suggested labels show:
- **Overall Positive**: 14 candidates (verified individual people meeting interest and location constraints).
- **Overall Negative**: 65 candidates (organizations, businesses, fan pages, news articles, or non-individuals).
- **Overall Ambiguous**: 1 candidate (borderline mixed identity requiring human review).
- **Annotation Status**: 80 candidates marked `needs_human_review` (100%).

---

## 7. Known Dataset Limitations

1. **Domain Imbalance**: The 80 candidates originate from the 4 specific search domains present in Phase 4 recordings. Generalization to other domains (e.g., healthcare, legal) should be evaluated in subsequent iterations.
2. **Snippet Information Density**: Some social media snippets (e.g. Instagram reels or Threads replies) contain very short text, making location or interest confirmation ambiguous without full page crawling. Such cases are deliberately labelled `ambiguous` or `negative` in accordance with our evidence-backed policy.
