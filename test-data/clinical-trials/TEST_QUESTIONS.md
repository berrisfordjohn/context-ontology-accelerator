# Test Questions

Ground truth is in `expected_answers.json` (generated from the CSVs). Expected tier is where COA should resolve the question.

## Tier 1 — Metrics (governed definitions, `metrics.json`)
| # | Question | Expected |
|---|---|---|
| 1 | How many subjects are enrolled? | `total_subjects` = 574 |
| 2 | How many adverse events are there in total? | `total_adverse_events` |
| 3 | How many serious adverse events have been reported? | sum of `serious_adverse_events_per_study` |
| 4 | What is the overall discontinuation rate? | sum of `discontinued_subjects_per_study` / 574 |
| 5 | How many major protocol deviations are there? | sum of `major_protocol_deviations_per_study` |

## Tier 2 — Structured queries (joins across tables)
| # | Question | Expected key |
|---|---|---|
| 6 | How many subjects are in each study? | `subjects_per_study` |
| 7 | How many subjects were randomised to each arm of ST-001? | `subjects_per_arm` |
| 8 | How many herpes zoster events occurred in each treatment arm? | `herpes_zoster_events_by_arm` |
| 9 | Compare neutropenia events between the two arms of study ST-002 | `neutropenia_events_by_arm_ST-002` |
| 10 | How many subjects had amyloid related imaging abnormalities in ST-004? | `subjects_with_ARIA_ST-004` |
| 11 | How many high ALT lab results per arm in ST-001? | `high_ALT_results_by_arm_ST-001` |
| 12 | What are the top 5 most frequent adverse event terms? | `top5_adverse_event_terms` |
| 13 | Which studies test the compound Cardiprex? (join studies to compounds) | `studies_using_Cardiprex` |
| 14 | How many sites are in each country? | `sites_per_country` |
| 15 | For ST-001, what is the mean change from baseline to Week 24 per arm? | `mean_week24_change_ST-001` |
| 16 | How many subjects discontinued because of an adverse event, per study? | `discontinued_due_to_AE_per_study` |
| 17 | Which system organ class has the most adverse events? (join to meddra_dictionary) | `top3_system_organ_classes` |
| 18 | List serious adverse events for Zorvantil 10 mg subjects at sites in Germany | verify against CSV with a join query |

## Tier 3 — Documents / knowledge retrieval
| # | Question | Expected source |
|---|---|---|
| 19 | What safety risks are specific to Zorvantil and what should investigators do? | zorvantil_safety_communication.md (herpes zoster, ALT > 120 U/L repeat within 72 h) |
| 20 | How is a treatment-emergent adverse event defined? | data_management_conventions.md (start date on/after randomization) |
| 21 | Why was the 10 mg dose chosen for Cardiprex in ST-003? | ST-003 protocol synopsis (selected from ST-005 PD data) |
| 22 | What imaging monitoring is required in the Neurolynt study? | ST-004 synopsis (MRI before dosing Weeks 4, 12, 24; ARIA) |
| 23 | What is the primary endpoint of ST-002 and how is it measured? | ST-002 synopsis |

## Hybrid / reasoning
| # | Question | Notes |
|---|---|---|
| 24 | Is the herpes zoster signal for Zorvantil visible in the data, and what does the protocol say about it? | data (Tier 2) + docs (Tier 3) |
| 25 | Is a small creatinine rise expected for Cardiprex? Do the lab results show it? | docs + `lab_results` |
| 26 | Which compound appears in both a Phase 1 and a Phase 3 study? | graph traversal across Study → Compound |

## Governance checks
- A `data-analyst` user can query but cannot induce/accept ontologies (403).
- A user with no grant on the namespace cannot see it.
- `includeDebugInfo` returns SQL only for admins/owners/stewards.
