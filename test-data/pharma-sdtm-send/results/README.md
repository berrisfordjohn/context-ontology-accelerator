# Experiment write-up: pharma SDTM / SEND / USDM on COA

## Goal
Test whether COA (AWS Context Ontology Accelerator) can answer questions over realistic pharma data: CDISC SDTM (human), SEND (animal), USDM (study operations) and master drug data with lifecycle-dependent IDs, delivered two ways. Headline question: patients with BMI over 30 per study, with acronym, drug name and ID, status and first-subject-in year, across US (imperial) and EU (metric) sites.

## Setup
- Synthetic data from `generate_data.py` (7 clinical studies / 544 patients, 6 in vivo studies / 186 animals, 5 drugs). Ground truth in `expected_answers.json`; 22 questions in `TEST_QUESTIONS.md`.
- **Scenario 1:** one source per study and per data type (15 Glue databases). **Scenario 2:** all studies combined (4 databases).
- COA deployed to eu-north-1 (16 stacks), Sonnet 4.6 + Cohere Embed v4, one namespace per scenario. Sources scanned and approved, ontology induced.
- Planned comparison: ungrounded induction vs grounded with `pharma_ontology.ttl` (separates Patient/Animal, ClinicalStudy/InVivoStudy).
- Two deployments were run (`coa3`, `coa4`); the second ran the questions paced (one per ~20 s, timeouts retried up to 3x).

## Results (ungrounded baseline, paced run; raw redacted answers in `raw_s1_paced.json`, `raw_s2_paced.json`)
| Outcome | Scenario 1 (15 sources) | Scenario 2 (4 sources) |
|---|---|---|
| Correct | 3 (Q16, Q17, Q22) | 6 (Q2, Q10, Q14, Q16, Q17, Q22) |
| Wrong / partial / empty | 7 (Q1 returned 60 not 544; Q6, Q14 one study only; Q7 = 0; Q15, Q19, Q20 empty) | 3 (Q7 = 0; Q15, Q20 empty) |
| HTTP 400 ambiguous table | 10 | 10 |
| HTTP 504 timeout | 2 | 3 |

The first, unpaced run was similar (2-3 correct per scenario). The headline BMI question (Q3) never succeeded: a 400 ambiguity error in both scenarios, or a timeout.

## Findings
1. **Same-named tables across sources break tier-2 queries.** `dm`, `ex`, `lb` exist in both SDTM and SEND (and per study in scenario 1). The generated SQL uses them unqualified and the engine rejects them as ambiguous. This is the human vs in vivo problem the data was designed to expose.
2. **Scenario 2 (combined) beat scenario 1 (separate).** In scenario 1 queries often hit a single study's source, giving partial answers (Q1 = 60 instead of 544, Q6, Q14).
3. The model ignored `ARMCD = 'SCRNFAIL'` (Q7 = 0 vs 44), and missed the drug-ID join across lifecycle schemes (Q15, Q19, Q20 empty).
4. Questions that worked used uniquely named tables (`bw`, `usdm_*`) or one source.
5. Q4 and Q8 timed out on every attempt; they are not just throttling noise.

## Not completed
- **Grounded run:** induction with the reference ontology failed with `ThrottlingException` in the LLM rerank on every attempt (7 per scenario in this deploy, plus 11 earlier). The account's Sonnet 4.6 quota is 10 requests/minute (L-00FF3314, L-F6E116D7); an increase was requested and refused. So it is **unknown** whether grounding fixes the ambiguity. The reference ontology itself loaded fine (28 classes).
- Metrics (`metrics_s1.json`, `metrics_s2.json`) were never registered or tested.

## Recommended next steps
1. Get the Bedrock quota raised (AWS Support case) or use a model with a higher limit, then run grounded induction and re-score.
2. Consider making table names unique per source (e.g. `sdtm_dm`, `send_dm`) to test whether the ambiguity is purely a naming issue.
3. Test the metrics (tier 1), especially the BMI CTE.

## Operations notes
- Each redeploy needed a new prefix (`coa`, `coa2`, `coa3`, `coa4`) because `*-dev-network` stacks stay `DELETE_FAILED` until AgentCore ENIs release (~8 h). Re-run `destroy.sh` for each prefix later. VPC limit is 5.
- The serve role needs an inline S3/Glue read policy for the data buckets after each deploy.
- Presigned ontology upload URLs return a 307 to the regional endpoint; use `aws s3 cp` to the artifacts bucket instead.
- Sessions expire (~1 h tokens, AWS login hours); a teardown run on an expired login aborts without deleting anything.

## Teardown status
Full teardown done (including data buckets, Glue databases, WAF ACLs and SSM parameters). Remaining and free: the CDK bootstrap, CloudWatch log groups, and four `*-dev-network` stacks (`coa`, `coa2`, `coa3`, `coa4`) stuck in DELETE_FAILED.
