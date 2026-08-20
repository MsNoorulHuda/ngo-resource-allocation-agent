# Testing

This document records how the system was tested, the datasets used, and the bugs found and fixed during that process. Testing was done manually by running real questions against the system and comparing the output to the expected answer, calculated independently from the raw data.

## Test Datasets

Three deliberately different datasets were used to test the system beyond simple, hand-built sample data:

| Dataset | Rows | Purpose |
|---|---|---|
| `needs.csv` + `distribution.csv` | 36 | Original hand-built sample, standard column names, two-file architecture |
| `ngo_allocation_large.csv` | 1,729 | Standard column names, single combined file, larger scale |
| `ngo_messy_dataset.csv` | 3,046 | Inconsistent column names, inconsistent area name casing/spelling, mixed date formats |
| `ngo_complex_multi_source.csv` | 10,000 | Fully renamed columns, large scale (stress test for schema mapping and report size limits) |

## Test Categories

Each dataset was tested with a mix of:
- **Basic lookups** — "What is the medicine shortage in Multan?"
- **Comparisons** — "Which area has the largest food shortage?" / "Which resource has the smallest gap in Lahore?"
- **Trend questions** — "Is the medicine shortage in Lahore getting worse?"
- **Trend comparisons** — "Which area has the biggest increase/decrease in food shortage over time?"
- **Combined conditions** — "Which area has a worsening food shortage and currently has the largest gap?"
- **Pairwise comparisons** — "Compare Lahore and Multan. Which area has the greater overall shortage?"

## Bugs Found and Fixed

### 1. Token limit exceeded on large datasets
**Symptom:** Questions without a specific area/date returned every matching row to the LLM, exceeding Groq's token-per-minute limit on the 1,729-row dataset.
**Fix:** Capped the number of individual rows shown in any report/answer (50 in the report, 20 in the final answer), with a note when truncated. Summary counts still reflect the full dataset.

### 2. Validator falsely rejecting correct answers
**Symptom:** The semantic (LLM-based) fact-checker occasionally rejected draft answers that were factually correct, sometimes contradicting itself in its own explanation.
**Fix:** Replaced number/date verification with deterministic Python checks (regex-based extraction and comparison) instead of relying on the LLM to judge whether a number appears in the source text. The LLM is now only used for genuinely semantic checks.

### 3. Single combined-file datasets not supported
**Symptom:** The three new test datasets each contain both `needed_quantity` and `distributed_quantity` in one file, but the system was built assuming two separate files.
**Fix:** Added `gap_analysis_from_combined()` and automatic detection of whether one file or two files were supplied, so the same pipeline works for both cases.

### 4. "Which resource has the largest shortage in X?" returned a row dump instead of an answer
**Symptom:** Resource-level comparison questions (comparing resources within one area) were not recognized — only area-level comparison (comparing areas for one resource) existed.
**Fix:** Added a `resource_comparison()` tool, mirroring the existing `area_comparison()` tool, and added deterministic + LLM-based detection of which comparison type a question needs.

### 5. "Smallest" comparisons always returned the largest result
**Symptom:** The system always picked the top of the ranking regardless of whether the question asked for "largest" or "smallest."
**Fix:** Added direction detection (largest/smallest) and selected the correct end of the ranking accordingly.

### 6. Trend questions failed final validation
**Symptom:** Trend answers (e.g. "gap changed from 20 to 160") were rejected because the validator expected a single row's needed/distributed/gap triplet, which trend answers don't have.
**Fix:** Added a dedicated trend-validation path that checks trend numbers against the trend calculation itself, not against a single data row.

### 7. "Biggest decrease" / "decline" answered with an increase
**Symptom:** Trend-comparison questions asking for a decrease returned the area with the biggest increase instead.
**Fix:** Initially patched with a keyword list, which proved too narrow (missed "decline," "drop," "improvement," etc.). Replaced with LLM-based direction detection (the LLM determines whether the question wants increase or decrease), with the keyword list kept only as a fallback if the LLM's response can't be parsed.

### 8. "Largest surplus" answered with a shortage
**Symptom:** Questions asking for a surplus specifically (e.g. "largest surplus for Food") returned the largest shortage instead, because the comparison logic wasn't aware of the shortage/surplus distinction.
**Fix:** Added a `comparison_metric` (shortage / surplus / gap) alongside direction, so the system filters to only surplus rows (or only shortage rows) before selecting a winner. If no matching records exist for the requested metric (e.g. no surplus exists anywhere), the system now explicitly says so instead of silently falling back to a shortage.

### 9. "Smallest gap" mislabeled as "smallest shortage"
**Symptom:** When a question asked generically for "gap" (not specifically shortage or surplus), the answer text still said "shortage" if the winning value happened to be positive.
**Fix:** The final answer now preserves the metric the user actually asked about (gap / shortage / surplus) rather than inferring wording from the sign of the result.

## Known Limitations

- **Area name normalization:** The messy dataset contains area names that differ only in spelling or capitalization (e.g. "Gujranwala" vs "Gujranwla", "Sialkot" vs "Sialkoat"). These are currently treated as distinct areas rather than being merged, since they were not run through the same fuzzy-matching process used for column names. This is a known data-quality limitation, listed in the roadmap.
- **Keyword-based fallbacks:** Where LLM-based detection is used (trend direction, comparison metric), a keyword-list fallback exists for cases where the LLM's response can't be parsed. This fallback is inherently less complete than semantic understanding and may not catch every possible phrasing.
- **Rate limits:** Testing was occasionally interrupted by the Groq API's free-tier rate limits (requests per minute / tokens per day) rather than by application logic errors. These are noted separately in test records and are not counted as application bugs.
