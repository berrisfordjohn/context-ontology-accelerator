# Pharma SDTM / SEND / USDM test dataset (for review)

Synthetic, deterministic (`generate_data.py`, seed 20261025). Same underlying data delivered two ways.

## Data types
| Type | Standard | Tables | Content |
|---|---|---|---|
| Clinical studies | CDISC SDTM | DM, EX, VS (long), AE, LB, DS | 7 studies (Ph1-3), 544 enrolled patients + ~8% screen failures |
| In vivo studies | CDISC SEND | DM (SPECIES, STRAIN), EX, BW, LB, CL | 6 studies (rat/mouse/dog), 186 animals |
| Master drug | custom | master_drug (IRI), master_drug_identifier | 5 drugs; ID scheme by lifecycle: PRECLINICAL (in vivo), CLINICAL_PH12 (Ph1/2), PUBLIC_PH3 (Ph3) |
| Study operations | CDISC USDM | usdm_study (acronym, phase, status), usdm_study_milestone (FSI/LSI/LSLV/DBL planned + actual) | 7 clinical studies |

`EX.EXTRT` holds the drug ID in the scheme appropriate to the study, so drug name needs a join through `master_drug_identifier.ID_VALUE`.

## Scenarios
- **Scenario 1 - separate**: one Glue database / COA source per study and per type: `s1_sdtm_cs101`... (7), `s1_send_iv001`... (6), `s1_master`, `s1_usdm` = **15 sources**. Tests cross-source discovery and per-study metrics (`metrics_s1.json`).
- **Scenario 2 - combined**: `s2_sdtm`, `s2_send`, `s2_master`, `s2_usdm` = **4 sources**, all studies in one set of files (`metrics_s2.json`).
- One bucket per scenario (COA allows one namespace tag per bucket/database).
- Each scenario is run ungrounded and grounded with `pharma_ontology.ttl`.

## Deliberate difficulty
- Tables `dm`, `ex`, `lb` exist in both SDTM (humans) and SEND (animals) with the same column names; the ontology (Patient vs Animal, ClinicalStudy vs InVivoStudy) must separate them.
- US sites: height in inches, weight in lb. EU/UK: cm (some in m), kg. `VSSTRESN` (standardised) populated only for non-US rows. Must convert.
- ~3% of patients lack baseline height; screen failures only have SCREENING rows (not patients).
- Creatinine in mg/dL (US) vs umol/L; drug ID differs per study phase; Neurolynt has no public ID; Vexalin is in vivo only.
- Placebo/vehicle arms are not attributed to a drug.

## Headline test
BMI > 30 patients by study: study id, acronym, patients, drug name, drug id, status, FSI year (226 patients over 7 studies; answer in `expected_answers.json` -> `q_bmi_over_30`). Drug id is the ID used in that study (CD-* for Ph1/2, public name for Ph3).

## Questions (answers in `expected_answers.json`)
1. Enrolled patients; 2. animals; 3. **BMI>30 headline**; 4. BMI>30 total; 5. BMI>30 per country; 6. patients per study; 7. screen failures; 8. mean baseline BMI per study; 9. mean baseline weight kg per study; 10. mean day-1 animal body weight (g) per study; 11. treated patients per drug; 12. treated animals per drug; 13. Zorvantil exposure split human vs animal; 14. SAEs per study acronym; 15. discontinued patients per acronym; 16. ongoing studies and FSI year; 17. studies where LSI later than planned; 18. patients with ALT > 3xULN per drug; 19. drugs in both in vivo and clinical; 20. drugs in vivo only; 21. male animals per species; 22. completed Ph3 with FSI before 2022.

Tier 1 = metrics (single source/table); multi-table questions (3, 11-13, 16-22) need tier 2 grounded NL-to-SQL. In scenario 1 tier-2 must span sources, expected to be harder. `metrics_s2.json` BMI metric uses a CTE - unverified against COA's SQL validator.

## Files
`generate_data.py`, `data/`, `schema.json`, `expected_answers.json`, `metrics_s1.json`, `metrics_s2.json`, `pharma_ontology.ttl`, `load_pharma.py` (`--scenario 1|2`).
