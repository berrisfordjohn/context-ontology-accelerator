"""Generate a fully synthetic, linked clinical-trial dataset (CDISC-inspired).

Standard library only. Deterministic: the same seed always yields the same files.
All compounds, people, sites and identifiers are fictional.

Usage:  python generate_data.py   # writes ./data/*.csv, schema.json, expected_answers.json
"""

import csv
import json
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

SEED = 20260101
OUT = Path(__file__).parent / "data"
rng = random.Random(SEED)

COMPOUNDS = [
    # id, name, inn, class, mechanism, target, atc
    ("CPD-101", "Zorvantil", "zorvantinib", "JAK inhibitor", "Selective JAK1 inhibition", "JAK1", "L04AA99"),
    ("CPD-102", "Oncotra", "oncotrazumab", "PD-L1 antibody", "PD-L1 checkpoint blockade", "PD-L1", "L01FF99"),
    ("CPD-103", "Cardiprex", "cardiprexin", "SGLT2 inhibitor", "Sodium-glucose cotransporter 2 inhibition", "SGLT2", "A10BK99"),
    ("CPD-104", "Neurolynt", "neurolyntamab", "Anti-amyloid antibody", "Amyloid-beta plaque clearance", "Amyloid-beta", "N06DX99"),
    ("CPD-900", "Docetaxel", "docetaxel", "Taxane", "Microtubule stabilisation", "Tubulin", "L01CD02"),
]

# study_id, nct, title, phase, area, indication, sponsor, status, start, planned_n, endpoint, unit, drug, n_subjects
STUDIES = [
    ("ST-001", "NCT09000001", "A Phase 3 Study of Zorvantil in Moderate-to-Severe Rheumatoid Arthritis", "Phase 3",
     "Immunology", "Rheumatoid arthritis", "Helvetia Biopharma", "Completed", date(2023, 2, 1), 160,
     "Change from baseline in DAS28-CRP", "score", "CPD-101", 150),
    ("ST-002", "NCT09000002", "A Phase 2 Study of Oncotra versus Docetaxel in PD-L1 Positive NSCLC", "Phase 2",
     "Oncology", "Non-small cell lung cancer", "Helvetia Biopharma", "Active, not recruiting", date(2024, 3, 15), 90,
     "Change from baseline in sum of target lesion diameters", "mm", "CPD-102", 80),
    ("ST-003", "NCT09000003", "A Phase 3 Cardiovascular Outcomes Study of Cardiprex in Heart Failure", "Phase 3",
     "Cardiology", "Heart failure", "Nordlicht Therapeutics", "Active, not recruiting", date(2024, 1, 10), 220,
     "Change from baseline in NT-proBNP", "pg/mL", "CPD-103", 200),
    ("ST-004", "NCT09000004", "A Phase 2 Study of Neurolynt in Early Alzheimer's Disease", "Phase 2",
     "Neurology", "Alzheimer's disease", "Nordlicht Therapeutics", "Recruiting", date(2025, 4, 1), 140,
     "Change from baseline in CDR-SB", "score", "CPD-104", 120),
    ("ST-005", "NCT09000005", "A Phase 1 Single Ascending Dose Study of Cardiprex in Healthy Volunteers", "Phase 1",
     "Cardiology", "Healthy volunteers", "Nordlicht Therapeutics", "Completed", date(2023, 9, 4), 24,
     "Change from baseline in 24h urinary glucose excretion", "g/24h", "CPD-103", 24),
]

# study_id -> [(arm suffix, name, type, drug_id, dose, allocation weight)]
ARMS = {
    "ST-001": [("A1", "Placebo", "Placebo Comparator", None, None, 1), ("A2", "Zorvantil 5 mg", "Experimental", "CPD-101", 5, 1),
               ("A3", "Zorvantil 10 mg", "Experimental", "CPD-101", 10, 1)],
    "ST-002": [("A1", "Oncotra 1200 mg", "Experimental", "CPD-102", 1200, 1), ("A2", "Docetaxel 75 mg/m2", "Active Comparator", "CPD-900", 75, 1)],
    "ST-003": [("A1", "Placebo", "Placebo Comparator", None, None, 1), ("A2", "Cardiprex 10 mg", "Experimental", "CPD-103", 10, 1)],
    "ST-004": [("A1", "Placebo", "Placebo Comparator", None, None, 1), ("A2", "Neurolynt 10 mg/kg", "Experimental", "CPD-104", 10, 1)],
    "ST-005": [("A1", "Cardiprex 5 mg", "Experimental", "CPD-103", 5, 1), ("A2", "Cardiprex 10 mg", "Experimental", "CPD-103", 10, 1),
               ("A3", "Cardiprex 20 mg", "Experimental", "CPD-103", 20, 1)],
}

COUNTRIES = {
    "ST-001": ["Germany", "Poland", "United Kingdom", "Spain", "United States"],
    "ST-002": ["Germany", "France", "Japan", "United States"],
    "ST-003": ["United States", "Germany", "Sweden", "Brazil", "United Kingdom", "Canada"],
    "ST-004": ["United States", "United Kingdom", "Netherlands", "Canada"],
    "ST-005": ["United Kingdom"],
}
CITIES = {
    "Germany": ["Berlin", "Munich", "Hamburg"], "Poland": ["Warsaw", "Krakow"], "United Kingdom": ["London", "Manchester", "Edinburgh"],
    "Spain": ["Madrid", "Barcelona"], "United States": ["Boston", "Houston", "Chicago", "San Diego"], "France": ["Paris", "Lyon"],
    "Japan": ["Tokyo", "Osaka"], "Sweden": ["Stockholm", "Gothenburg"], "Brazil": ["Sao Paulo", "Rio de Janeiro"],
    "Canada": ["Toronto", "Montreal"], "Netherlands": ["Amsterdam", "Utrecht"],
}
SURNAMES = ["Alder", "Brandt", "Castellan", "Dumont", "Eklund", "Fontaine", "Grayson", "Hartmann", "Ito", "Jansen", "Kowalski",
            "Lindqvist", "Moreau", "Nakamura", "Okafor", "Petrov", "Quinn", "Rossi", "Silva", "Tanaka", "Ulrich", "Varga"]

# (PT, SOC, MedDRA-style code, baseline weight)
MEDDRA = [
    ("Headache", "Nervous system disorders", "10019211", 10), ("Dizziness", "Nervous system disorders", "10013573", 5),
    ("Nausea", "Gastrointestinal disorders", "10028813", 9), ("Diarrhoea", "Gastrointestinal disorders", "10012735", 7),
    ("Vomiting", "Gastrointestinal disorders", "10047700", 4),
    ("Nasopharyngitis", "Infections and infestations", "10028810", 8),
    ("Upper respiratory tract infection", "Infections and infestations", "10046306", 6),
    ("Pneumonia", "Infections and infestations", "10035664", 2), ("Herpes zoster", "Infections and infestations", "10019974", 1),
    ("Alanine aminotransferase increased", "Investigations", "10001551", 4),
    ("Neutropenia", "Blood and lymphatic system disorders", "10029354", 3), ("Anaemia", "Blood and lymphatic system disorders", "10002272", 3),
    ("Fatigue", "General disorders and administration site conditions", "10016256", 8),
    ("Rash", "Skin and subcutaneous tissue disorders", "10037844", 5),
    ("Hypertension", "Vascular disorders", "10020772", 4), ("Hypotension", "Vascular disorders", "10021097", 3),
    ("Atrial fibrillation", "Cardiac disorders", "10003658", 2), ("Confusional state", "Psychiatric disorders", "10010305", 2),
    ("Genital mycotic infection", "Infections and infestations", "10018087", 1),
    ("Amyloid related imaging abnormalities", "Nervous system disorders", "10083555", 1),
]
# injected safety signals: weight multipliers per drug
DRUG_SIGNALS = {
    "CPD-101": {"Herpes zoster": 8, "Alanine aminotransferase increased": 4, "Upper respiratory tract infection": 2},
    "CPD-102": {"Rash": 3, "Fatigue": 2},
    "CPD-103": {"Genital mycotic infection": 12, "Hypotension": 2},
    "CPD-104": {"Amyloid related imaging abnormalities": 40, "Headache": 2, "Confusional state": 2},
    "CPD-900": {"Neutropenia": 10, "Anaemia": 3, "Nausea": 2, "Vomiting": 2},
}

LAB_TESTS = [  # code, name, unit, low, high, mean, sd
    ("ALT", "Alanine aminotransferase", "U/L", 7, 40, 24, 7), ("AST", "Aspartate aminotransferase", "U/L", 10, 40, 24, 6),
    ("CREAT", "Creatinine", "umol/L", 45, 110, 80, 12), ("HGB", "Haemoglobin", "g/L", 120, 170, 140, 12),
    ("ANC", "Absolute neutrophil count", "10^9/L", 2.0, 7.5, 4.2, 1.0),
]
LAB_VISITS = [("SCREENING", -14), ("WEEK 4", 28), ("WEEK 12", 84), ("WEEK 24", 168)]
EFF_VISITS = [("BASELINE", 0), ("WEEK 12", 84), ("WEEK 24", 168)]

EFF_BASE = {"ST-001": (5.6, 0.8), "ST-002": (62.0, 18.0), "ST-003": (1450.0, 420.0), "ST-004": (3.4, 0.9), "ST-005": (45.0, 8.0)}
EFF_CHANGE = {  # week-24 mean change by arm suffix
    "ST-001": {"A1": -0.4, "A2": -1.4, "A3": -2.1}, "ST-002": {"A1": -14.0, "A2": -6.0},
    "ST-003": {"A1": -90.0, "A2": -310.0}, "ST-004": {"A1": 0.9, "A2": 0.45}, "ST-005": {"A1": 18.0, "A2": 38.0, "A3": 66.0},
}
DEVIATIONS = [("Missed visit window", "Minor"), ("Out-of-window dosing", "Minor"), ("Prohibited concomitant medication", "Major"),
              ("Informed consent version error", "Major"), ("Missed safety lab", "Minor"), ("Inclusion criterion not met", "Major")]
DISC_REASONS = ["Adverse event", "Withdrawal by subject", "Lack of efficacy", "Lost to follow-up", "Protocol deviation"]
RACES = ["White", "Asian", "Black or African American", "Other"]
REPORT_DATE = date(2026, 1, 31)  # data cut-off


def d(x):
    return x.isoformat() if x else ""


def wchoice(items, weights):
    return rng.choices(items, weights=weights, k=1)[0]


def write(name, header, rows):
    OUT.mkdir(exist_ok=True)
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(header)
        w.writerows(rows)
    print(f"{name}.csv: {len(rows)} rows")


def main():
    drug_name = {c[0]: c[1] for c in COMPOUNDS}
    studies, arms, sites, subjects = [], [], [], []
    aes, labs, effs, devs = [], [], [], []
    ae_seq = lab_seq = eff_seq = dev_seq = 0
    arm_drug = {}

    for (sid, nct, title, phase, area, indication, sponsor, status, start, planned, endpoint, unit, drug, nsub) in STUDIES:
        studies.append([sid, nct, title, phase, area, indication, sponsor, status, d(start), planned, endpoint, unit, drug])
        arm_defs = ARMS[sid]
        for suf, name, atype, adrug, dose, _w in arm_defs:
            arm_id = f"{sid}-{suf}"
            arms.append([arm_id, sid, name, atype, adrug or "", dose if dose is not None else ""])
            arm_drug[arm_id] = adrug

        n_sites = {"ST-001": 10, "ST-002": 7, "ST-003": 14, "ST-004": 9, "ST-005": 1}[sid]
        study_sites = []
        for i in range(1, n_sites + 1):
            country = COUNTRIES[sid][(i - 1) % len(COUNTRIES[sid])]
            city = rng.choice(CITIES[country])
            site_id = f"{sid}-S{i:02d}"
            activation = start + timedelta(days=rng.randint(-60, 45))
            site_status = "Closed" if status == "Completed" else ("Active" if i % 7 else "On hold")
            sites.append([site_id, sid, f"{city} Clinical Research Centre {i}", country, city, f"Dr. {rng.choice(SURNAMES)}", site_status, d(activation)])
            study_sites.append((site_id, country, activation))

        enroll_span = 300 if phase != "Phase 1" else 40
        for n in range(1, nsub + 1):
            site_id, country, activation = rng.choice(study_sites)
            subj = f"{sid}-{n:04d}"
            if phase == "Phase 1":
                suf = arm_defs[(n - 1) % len(arm_defs)][0]
            else:
                suf = wchoice([a[0] for a in arm_defs], [a[5] for a in arm_defs])
            arm_id = f"{sid}-{suf}"
            consent = max(activation, start) + timedelta(days=rng.randint(0, enroll_span))
            consent = min(consent, REPORT_DATE - timedelta(days=30))
            rand_date = consent + timedelta(days=rng.randint(7, 21))
            age_mu = {"Rheumatoid arthritis": 54, "Non-small cell lung cancer": 66, "Heart failure": 69, "Alzheimer's disease": 72}.get(indication, 32)
            age = max(18, min(90, int(rng.gauss(age_mu, 8))))
            sex = wchoice(["F", "M"], [0.68, 0.32] if area == "Immunology" else [0.42, 0.58])
            race = wchoice(RACES, [0.7, 0.14, 0.1, 0.06])
            if status == "Completed":
                outcome = wchoice(["Completed", "Discontinued"], [0.84, 0.16])
            else:
                outcome = wchoice(["Ongoing", "Completed", "Discontinued"], [0.62, 0.14, 0.24])
            reason = ""
            if outcome == "Discontinued":
                reason = rng.choice(DISC_REASONS)
                last_contact = min(rand_date + timedelta(days=rng.randint(20, 150)), REPORT_DATE)
            elif outcome == "Completed":
                last_contact = min(rand_date + timedelta(days=168), REPORT_DATE)
            else:
                last_contact = REPORT_DATE
            subjects.append([subj, sid, site_id, arm_id, age, sex, race, country, d(consent), d(rand_date), outcome, reason, d(last_contact)])

    subj_index = {s[0]: s for s in subjects}

    for s in subjects:
        subj, sid, _site, arm_id = s[0], s[1], s[2], s[3]
        rand_date = date.fromisoformat(s[9])
        last = date.fromisoformat(s[12])
        drug = arm_drug[arm_id]
        signals = DRUG_SIGNALS.get(drug, {}) if drug else {}
        weights = [m[3] * signals.get(m[0], 1) for m in MEDDRA]
        expected = 1.1 + (0.5 if drug else 0.0) + (1.2 if drug == "CPD-900" else 0.0)
        n_ae = min(6, int(rng.expovariate(1 / expected)))
        window = max((last - rand_date).days, 1)
        for _ in range(n_ae):
            pt, soc, code, _w = MEDDRA[rng.choices(range(len(MEDDRA)), weights=weights, k=1)[0]]
            if pt == "Amyloid related imaging abnormalities" and sid != "ST-004":
                continue
            start_d = rand_date + timedelta(days=rng.randint(1, window))
            sev = wchoice(["Mild", "Moderate", "Severe"], [0.55, 0.33, 0.12])
            serious_p = 0.05 + (0.35 if sev == "Severe" else 0) + (0.3 if pt in ("Pneumonia", "Atrial fibrillation") else 0)
            serious = "Y" if rng.random() < serious_p else "N"
            related_p = 0.5 if drug else 0.15
            if drug and signals.get(pt, 1) > 1:
                related_p = 0.85
            related = "Y" if rng.random() < related_p else "N"
            resolved = rng.random() < 0.8
            end_d = min(start_d + timedelta(days=rng.randint(1, 30)), last) if resolved else None
            outcome = "Recovered/Resolved" if resolved else wchoice(["Not recovered/Not resolved", "Recovering/Resolving", "Fatal"], [0.55, 0.4, 0.05])
            if serious == "N" and outcome == "Fatal":
                outcome = "Not recovered/Not resolved"
            ae_seq += 1
            aes.append([f"AE-{ae_seq:06d}", subj, sid, pt, code, soc, sev, serious, related, d(start_d), d(end_d), outcome])

    for s in subjects:
        subj, sid, arm_id = s[0], s[1], s[3]
        rand_date = date.fromisoformat(s[9])
        last = date.fromisoformat(s[12])
        drug = arm_drug[arm_id]
        for visit, offset in LAB_VISITS:
            vdate = rand_date + timedelta(days=offset)
            if vdate > last:
                continue
            for code, name, unit, low, high, mu, sd in LAB_TESTS:
                v = rng.gauss(mu, sd)
                if offset > 0:
                    if code == "ALT" and drug == "CPD-101":
                        v *= 1.5 + offset / 300
                    if code == "ANC" and drug == "CPD-900":
                        v *= 0.55
                    if code == "CREAT" and drug == "CPD-103":
                        v *= 1.08
                v = round(max(v, 0.1), 1)
                flag = "H" if v > high else ("L" if v < low else "N")
                lab_seq += 1
                labs.append([f"LB-{lab_seq:07d}", subj, sid, visit, d(vdate), code, name, v, unit, low, high, flag])

    study_endpoint = {x[0]: (x[10], x[11]) for x in STUDIES}
    for s in subjects:
        subj, sid, arm_id = s[0], s[1], s[3]
        rand_date = date.fromisoformat(s[9])
        last = date.fromisoformat(s[12])
        mu, sd = EFF_BASE[sid]
        endpoint, unit = study_endpoint[sid]
        base = max(rng.gauss(mu, sd), mu * 0.3)
        change24 = EFF_CHANGE[sid][arm_id.split("-")[-1]]
        for visit, offset in EFF_VISITS:
            vdate = rand_date + timedelta(days=offset)
            if vdate > last:
                continue
            val = base + change24 * (offset / 168) * (base / mu) ** 0.5 + rng.gauss(0, sd * 0.12)
            eff_seq += 1
            effs.append([f"EF-{eff_seq:07d}", subj, sid, endpoint, visit, d(vdate), round(val, 2), unit, "Y" if offset == 0 else "N"])

    for s in subjects:
        if rng.random() < 0.12:
            desc, cat = rng.choice(DEVIATIONS)
            dstart = min(date.fromisoformat(s[9]) + timedelta(days=rng.randint(5, 120)), date.fromisoformat(s[12]))
            dev_seq += 1
            devs.append([f"PD-{dev_seq:05d}", s[0], s[1], s[2], desc, cat, d(dstart)])

    write("compounds", ["drug_id", "drug_name", "inn", "drug_class", "mechanism_of_action", "target", "atc_code"], [list(c) for c in COMPOUNDS])
    write("studies", ["study_id", "nct_id", "title", "phase", "therapeutic_area", "indication", "sponsor", "status", "start_date",
                      "planned_enrollment", "primary_endpoint", "endpoint_unit", "drug_id"], studies)
    write("study_arms", ["arm_id", "study_id", "arm_name", "arm_type", "drug_id", "dose_mg"], arms)
    write("sites", ["site_id", "study_id", "site_name", "country", "city", "principal_investigator", "site_status", "activation_date"], sites)
    write("subjects", ["subject_id", "study_id", "site_id", "arm_id", "age", "sex", "race", "country", "consent_date",
                       "randomization_date", "completion_status", "discontinuation_reason", "last_contact_date"], subjects)
    write("adverse_events", ["ae_id", "subject_id", "study_id", "preferred_term", "meddra_pt_code", "system_organ_class", "severity",
                             "is_serious", "is_related_to_treatment", "start_date", "end_date", "outcome"], aes)
    write("lab_results", ["lab_id", "subject_id", "study_id", "visit", "collection_date", "test_code", "test_name", "result_value",
                          "result_unit", "ref_range_low", "ref_range_high", "abnormal_flag"], labs)
    write("efficacy_results", ["efficacy_id", "subject_id", "study_id", "endpoint_name", "visit", "assessment_date", "value", "unit",
                               "is_baseline"], effs)
    write("protocol_deviations", ["deviation_id", "subject_id", "study_id", "site_id", "description", "category", "deviation_date"], devs)
    write("meddra_dictionary", ["meddra_pt_code", "preferred_term", "system_organ_class"], [[m[2], m[0], m[1]] for m in MEDDRA])

    def cols(spec):
        return [{"name": n, "type": t} for n, t in spec]

    schema = {
        "compounds": cols([("drug_id", "string"), ("drug_name", "string"), ("inn", "string"), ("drug_class", "string"),
                           ("mechanism_of_action", "string"), ("target", "string"), ("atc_code", "string")]),
        "studies": cols([("study_id", "string"), ("nct_id", "string"), ("title", "string"), ("phase", "string"),
                         ("therapeutic_area", "string"), ("indication", "string"), ("sponsor", "string"), ("status", "string"),
                         ("start_date", "date"), ("planned_enrollment", "int"), ("primary_endpoint", "string"),
                         ("endpoint_unit", "string"), ("drug_id", "string")]),
        "study_arms": cols([("arm_id", "string"), ("study_id", "string"), ("arm_name", "string"), ("arm_type", "string"),
                            ("drug_id", "string"), ("dose_mg", "double")]),
        "sites": cols([("site_id", "string"), ("study_id", "string"), ("site_name", "string"), ("country", "string"), ("city", "string"),
                       ("principal_investigator", "string"), ("site_status", "string"), ("activation_date", "date")]),
        "subjects": cols([("subject_id", "string"), ("study_id", "string"), ("site_id", "string"), ("arm_id", "string"), ("age", "int"),
                          ("sex", "string"), ("race", "string"), ("country", "string"), ("consent_date", "date"),
                          ("randomization_date", "date"), ("completion_status", "string"), ("discontinuation_reason", "string"),
                          ("last_contact_date", "date")]),
        "adverse_events": cols([("ae_id", "string"), ("subject_id", "string"), ("study_id", "string"), ("preferred_term", "string"),
                                ("meddra_pt_code", "string"), ("system_organ_class", "string"), ("severity", "string"),
                                ("is_serious", "string"), ("is_related_to_treatment", "string"), ("start_date", "date"),
                                ("end_date", "date"), ("outcome", "string")]),
        "lab_results": cols([("lab_id", "string"), ("subject_id", "string"), ("study_id", "string"), ("visit", "string"),
                             ("collection_date", "date"), ("test_code", "string"), ("test_name", "string"), ("result_value", "double"),
                             ("result_unit", "string"), ("ref_range_low", "double"), ("ref_range_high", "double"),
                             ("abnormal_flag", "string")]),
        "efficacy_results": cols([("efficacy_id", "string"), ("subject_id", "string"), ("study_id", "string"), ("endpoint_name", "string"),
                                  ("visit", "string"), ("assessment_date", "date"), ("value", "double"), ("unit", "string"),
                                  ("is_baseline", "string")]),
        "protocol_deviations": cols([("deviation_id", "string"), ("subject_id", "string"), ("study_id", "string"), ("site_id", "string"),
                                     ("description", "string"), ("category", "string"), ("deviation_date", "date")]),
        "meddra_dictionary": cols([("meddra_pt_code", "string"), ("preferred_term", "string"), ("system_organ_class", "string")]),
    }
    (Path(__file__).parent / "schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")

    arm_name = {a[0]: a[2] for a in arms}
    by_arm = lambda rows, idx_subj: Counter(arm_name[subj_index[r[idx_subj]][3]] for r in rows)  # noqa: E731

    def mean_change(study, arm_id):
        vals = defaultdict(dict)
        for e in effs:
            if e[2] == study and subj_index[e[1]][3] == arm_id:
                vals[e[1]][e[4]] = e[6]
        diffs = [v["WEEK 24"] - v["BASELINE"] for v in vals.values() if "WEEK 24" in v and "BASELINE" in v]
        return {"mean_change": round(sum(diffs) / len(diffs), 2), "n": len(diffs)}

    expected = {
        "_note": "Ground truth computed from the generated CSVs. Query answers should agree (allow rounding).",
        "total_subjects": len(subjects),
        "subjects_per_study": dict(Counter(s[1] for s in subjects)),
        "subjects_per_arm": dict(Counter(arm_name[s[3]] + " (" + s[1] + ")" for s in subjects)),
        "total_adverse_events": len(aes),
        "adverse_events_per_study": dict(Counter(a[2] for a in aes)),
        "serious_adverse_events_per_study": dict(Counter(a[2] for a in aes if a[7] == "Y")),
        "herpes_zoster_events_by_arm": dict(by_arm([a for a in aes if a[3] == "Herpes zoster"], 1)),
        "neutropenia_events_by_arm_ST-002": dict(by_arm([a for a in aes if a[3] == "Neutropenia" and a[2] == "ST-002"], 1)),
        "subjects_with_ARIA_ST-004": len({a[1] for a in aes if a[3] == "Amyloid related imaging abnormalities"}),
        "genital_mycotic_infection_events_by_arm_ST-003": dict(by_arm([a for a in aes if a[3] == "Genital mycotic infection" and a[2] == "ST-003"], 1)),
        "discontinued_subjects_per_study": dict(Counter(s[1] for s in subjects if s[10] == "Discontinued")),
        "discontinued_due_to_AE_per_study": dict(Counter(s[1] for s in subjects if s[11] == "Adverse event")),
        "major_protocol_deviations_per_study": dict(Counter(x[2] for x in devs if x[5] == "Major")),
        "sites_per_country": dict(Counter(s[3] for s in sites)),
        "high_ALT_results_by_arm_ST-001": dict(by_arm([l for l in labs if l[5] == "ALT" and l[11] == "H" and l[2] == "ST-001"], 1)),
        "top5_adverse_event_terms": Counter(a[3] for a in aes).most_common(5),
        "top3_system_organ_classes": Counter(a[5] for a in aes).most_common(3),
        "mean_week24_change_ST-001": {a[0]: mean_change("ST-001", a[0]) for a in arms if a[1] == "ST-001"},
        "mean_week24_change_ST-003": {a[0]: mean_change("ST-003", a[0]) for a in arms if a[1] == "ST-003"},
        "studies_using_Cardiprex": sorted({s[0] for s in studies if s[12] == "CPD-103"}),
        "drug_names": drug_name,
    }
    (Path(__file__).parent / "expected_answers.json").write_text(json.dumps(expected, indent=2), encoding="utf-8")
    print("schema.json + expected_answers.json written")


if __name__ == "__main__":
    main()
