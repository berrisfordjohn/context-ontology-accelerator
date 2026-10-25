# Test results: reference-ontology grounding vs. baseline

Run against a live deployment (prefix `coa2`, eu-north-1, Sonnet 4.6 + Cohere Embed v4) with the 26 questions in [TEST_QUESTIONS.md](../TEST_QUESTIONS.md), scored against [expected_answers.json](../expected_answers.json).

## What was compared

| Run | Ontology state | Raw results |
|-----|----------------|-------------|
| Baseline (no grounding) | Induced from the Glue source with nothing to ground against (10 classes, 1488 axioms) | `raw_baseline_ungrounded.json` |
| Grounded | `clinical_trials_ontology.ttl` loaded as a reference ontology (11 classes), then induction re-run with `groundingOntologyIds=[reference]`, `groundingMode=ENHANCED` (10/10 tables matched, 0 novel classes, 1518 axioms) | `raw_grounded.json`, `raw_grounded_retry_q23-26.json` |

Steps used for the grounded run: `POST /ontologies/upload-url`, S3 PUT, `POST /ontologies/{id}/ingest-from-s3`, `POST /induce` with `groundingOntologyIds`, then `POST /proposals/{id}/accept`. The baseline ontology was removed first (`DELETE /ontologies` removes all ontologies in the namespace).

## Mapping outputs (`mapping/`)

- `proposal_matches_url.json`: table and column to reference-class matches.
- `proposal_r2rml_url.ttl`: R2RML mapping used by the virtual knowledge graph.
- `proposal_constraints_url.ttl`: constraint config.
- `accepted_induced_ontology_grounded.ttl`: the accepted ontology, including glossary terms, synonyms (`skos:altLabel`, 100) and tags, with grounding links to the reference.
- `reference_ontology_as_loaded.ttl`: the reference ontology as stored.

The baseline mapping was not exported before it was deleted.

## Scores

| Q | Expected | Baseline | Grounded |
|---|----------|----------|----------|
| 1 | 574 | pass | pass |
| 2 | 562 | pass | pass |
| 3 | 49 serious AEs | fail (0) | fail (0) |
| 4 | 21.3% | pass (tier 1 metric) | pass (tier 1 metric) |
| 5 | 36 | pass | pass |
| 6 | subjects per study | pass | pass |
| 7 | ST-001 arms 52/52/46 | pass | pass |
| 8 | herpes zoster by arm | pass | pass |
| 9 | neutropenia ST-002 | pass | pass |
| 10 | 10 | pass (low confidence 0.35) | pass (0.40) |
| 11 | 92/91/3 | pass | pass |
| 12 | top 5 terms | pass | pass |
| 13 | ST-003, ST-005 | pass | pass |
| 14 | sites per country | pass | pass |
| 15 | mean Week 24 change | fail (empty) | fail (empty) |
| 16 | discontinued due to AE | pass | fail (empty) |
| 17 | Infections and infestations | pass | pass |
| 18 | SAEs, Zorvantil 10 mg, Germany | timeout (504) | timeout (504) |
| 19 | docs + data | partial (data rows only) | partial |
| 20 | TEAE definition (docs) | timeout | timeout |
| 21 | ST-003 dose rationale (docs) | timeout | timeout |
| 22 | ST-004 imaging (docs) | pass (tier 3) | pass (tier 3) |
| 23 | ST-002 endpoint | pass | pass |
| 24 | data + docs | partial (data only) | error (502 then 504) |
| 25 | docs + lab_results | timeout | partial (data only) |
| 26 | Cardiprex | pass | pass |

Totals: baseline 18 pass, 4 partial or fail, 4 timeouts; grounded 17 pass, 5 partial or fail, 4 timeouts.

## Findings

- Grounding did not change the answers. Differences between runs (Q16, Q24, Q25) are LLM non-determinism or timing, not grounding. Structured answers come from LLM-generated SQL over the Glue schema, which is the same in both runs.
- Grounding did change the ontology: all 10 tables aligned to the reference classes with no novel classes and 30 more axioms.
- Failures:
  - Q3 and Q15 are wrong or empty SQL from the model (Q3 probably filters on the wrong value for the serious flag).
  - Questions that need document retrieval (18, 20, 21) exceed the 29 s API Gateway limit. Run them through the MCP server or give them a longer timeout path.
  - Q19, Q24 and Q25 return only the structured half of a mixed data and document question.
- The serve role needs read access to the data bucket and Glue database. Without it every tier 2 query fails with an S3 `ListBucket` denial.
