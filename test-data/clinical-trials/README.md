# Clinical Trials Test Dataset

A fully **synthetic** (no real patient data), linked pharma dataset: 5 studies, 5 compounds, 12 arms, 41 sites, 574 subjects, adverse events, lab results, efficacy results, protocol deviations and a MedDRA-style dictionary, plus narrative documents for unstructured (Tier 3) retrieval. Compound names (Zorvantil, Oncotra, Cardiprex, Neurolynt) and NCT numbers are fictional.

## Contents

| File | Purpose |
|---|---|
| `generate_data.py` | Deterministic generator (seed `20260101`, stdlib only). Writes `data/*.csv`, `schema.json`, `expected_answers.json` |
| `data/*.csv` | 10 linked tables (below) |
| `schema.json` | Glue column types used by the loader |
| `documents/*.md` | 4 protocol synopses, data-management conventions, a Zorvantil safety communication |
| `clinical_trials_ontology.ttl` | Hand-written reference ontology (manual-upload path / gold standard) |
| `metrics.json` | 5 Tier-1 metric definitions |
| `load_to_aws.py` | Uploads to S3, creates Glue database + tables, tags, verifies in Athena |
| `TEST_QUESTIONS.md`, `expected_answers.json` | Test questions and ground truth |
| `DEPLOYMENT_PLAN.md` | End-to-end AWS deployment and test plan |

## Data model

```
compounds (drug_id) <----- studies (study_id, drug_id) ----< study_arms (arm_id, study_id, drug_id)
                              |  \                               |
                              |   `---< sites (site_id, study_id)|
                              v                                  v
                        subjects (subject_id, study_id, site_id, arm_id)
                              |
        .---------------------+----------------------.----------------------.
        v                     v                      v                      v
 adverse_events        lab_results           efficacy_results      protocol_deviations
 (ae_id, subject_id,   (lab_id, subject_id)  (efficacy_id,         (deviation_id, subject_id,
  study_id,                                   subject_id)           site_id)
  meddra_pt_code) ---> meddra_dictionary (meddra_pt_code)
```

| Table | Rows | Key columns |
|---|---|---|
| compounds | 5 | `drug_id` |
| studies | 5 | `study_id`, `nct_id`, `drug_id` |
| study_arms | 12 | `arm_id`, `study_id`, `drug_id` |
| sites | 41 | `site_id`, `study_id` |
| subjects | 574 | `subject_id`, `study_id`, `site_id`, `arm_id` |
| adverse_events | ~560 | `ae_id`, `subject_id`, `study_id`, `meddra_pt_code` |
| lab_results | ~10,000 | `lab_id`, `subject_id`, `study_id` |
| efficacy_results | ~1,450 | `efficacy_id`, `subject_id`, `study_id` |
| protocol_deviations | ~68 | `deviation_id`, `subject_id`, `site_id` |
| meddra_dictionary | 20 | `meddra_pt_code` |

Consistent column names across tables are deliberate, so COA's key inference finds the joins. Primary/foreign keys are not declared in Glue; COA infers them and you confirm them at review.

### Planted signals (so answers are checkable and meaningful)
- Zorvantil (JAK1): excess **herpes zoster** and **raised ALT**, higher at 10 mg. Documented in the safety communication.
- Docetaxel comparator: **neutropenia** and low ANC in ST-002.
- Cardiprex (SGLT2): **genital mycotic infections**, small creatinine rise (ST-003).
- Neurolynt: **ARIA** events (ST-004 only).
- Efficacy improves in a dose-dependent way on active arms.
- ST-005 (Phase 1) is a second study of the same compound as ST-003 — tests cross-study linking.

## How to load into the project

Prerequisites: COA deployed, namespace created (record `namespaceId`), AWS credentials for the same account and region.

```bash
cd test-data/clinical-trials
python generate_data.py            # optional: CSVs are already in data/
uv run --with boto3 python load_to_aws.py --region eu-north-1 --namespace-id <namespaceId> [--prefix coa]
```

The script is idempotent. It:
1. Creates `s3://coa-clinical-trials-<account>-<region>` (private, encrypted).
2. Uploads each CSV to `curated/<table>/data.csv` (one folder per table — required so each Glue table points to one file type) and the documents to `documents/`.
3. Creates Glue database `clinical_trials` and 10 tables with `OpenCSVSerde` and `skip.header.line.count=1`. (Do not use a Glue crawler: it picks a CSV format that splits quoted commas.)
4. Tags the Glue database and the bucket with `coa:namespace=<namespaceId>` (use `--prefix` if the deployment prefix is not `coa`). COA refuses to register untagged sources.
5. Counts rows of every table in Athena and compares with the CSVs.

Then in the COA web app (namespace `clinical-trials`):
1. **Sources > Connect Source > Glue Data Catalog**: catalog ID = account ID, region, database `clinical_trials`. Wait for scan and enrichment; review and approve tables.
2. **Sources > Connect Source > Documents**: S3 bucket `coa-clinical-trials-<account>-<region>`, prefix `documents/` (or upload the six files).
3. **Ontology > Induction**: strategy `table_to_ontology`; accept the proposal. Optionally upload `clinical_trials_ontology.ttl` to compare.
4. **Metrics**: create each entry of `metrics.json` (`POST /namespaces/{id}/metrics`) after replacing `REPLACE_WITH_SOURCE_ID`.
5. **Playground**: ask the questions in `TEST_QUESTIONS.md`.

If a column type fails (for example a `date` column reads as NULL): change those columns to `string` in `schema.json`, re-run the loader, and CAST in queries.

## Running the service locally vs on AWS
COA needs Neptune, OpenSearch Serverless, Bedrock AgentCore and DataZone, so there is no meaningful local mode for end-to-end tests; run it on AWS per `DEPLOYMENT_PLAN.md`. Unit tests (`make test`) run locally.
