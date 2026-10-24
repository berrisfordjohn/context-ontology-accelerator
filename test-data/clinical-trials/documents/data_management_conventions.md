# Clinical Data Management Conventions (all studies)

This document explains how the clinical trial data in the warehouse is structured and how common terms are defined.

## Tables and keys
- `studies` holds one row per study; `study_id` (for example ST-001) links every other table.
- `study_arms` holds the treatment arms of each study; `subjects.arm_id` is the arm a subject was randomised to.
- `compounds` is the drug reference list; `studies.drug_id` and `study_arms.drug_id` link to it. Placebo arms have no drug_id.
- `sites` are the investigator sites of a study; `subjects.site_id` is the site that enrolled the subject.
- `adverse_events`, `lab_results`, `efficacy_results` and `protocol_deviations` all link to a subject through `subject_id`.
- `adverse_events.meddra_pt_code` links to `meddra_dictionary`, which maps preferred terms to system organ classes.

## Definitions
- **Treatment-emergent adverse event (TEAE):** an adverse event whose start date is on or after the subject's randomization date.
- **Serious adverse event (SAE):** `is_serious = 'Y'` — results in death, is life-threatening, requires hospitalisation, or is otherwise medically important.
- **Related to treatment:** `is_related_to_treatment = 'Y'`, as judged by the investigator.
- **Discontinuation rate:** subjects with `completion_status = 'Discontinued'` divided by all randomised subjects in the study or arm.
- **Abnormal lab:** `abnormal_flag` of H (above reference range high) or L (below reference range low).
- **Major protocol deviation:** a deviation with `category = 'Major'` that may affect subject safety or data integrity; minor deviations are logged but not reported individually in the clinical study report.
- **Visits:** SCREENING (14 days before randomization), BASELINE (day of randomization), WEEK 4 (day 28), WEEK 12 (day 84), WEEK 24 (day 168).
- **Change from baseline:** the Week 24 efficacy value minus the BASELINE value for the same subject and endpoint.

## Data cut-off
All data in this dataset is cut off at 31 January 2026. Subjects with completion_status 'Ongoing' have not yet finished their Week 24 visit.

## Privacy
All subject, investigator and site identifiers in this warehouse are synthetic. No real patient data is present.
