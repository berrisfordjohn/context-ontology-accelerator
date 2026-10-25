"""Generate the synthetic CDISC dataset (SDTM + SEND + USDM + master drug data) for two scenarios.

Scenario 1 ("separate"): one Glue database per study for SDTM and SEND; USDM and master data shared.
Scenario 2 ("combined"): one Glue database for all SDTM studies, one for all SEND studies.
Both scenarios hold exactly the same underlying data, so one expected_answers.json covers both.

Outputs (deterministic, fixed seed):
  data/scenario1_separate/<db>/<table>.csv   data/scenario2_combined/<db>/<table>.csv
  schema.json            {scenario: {db: {table: [columns]}}}
  expected_answers.json  ground truth computed from the generated rows
  metrics_s1.json / metrics_s2.json   metric request bodies (placeholders for source ids)
Run: python generate_data.py
"""

import csv
import json
import random
import shutil
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
R = random.Random(20261025)
TODAY = date(2026, 10, 1)
KG_PER_LB, CM_PER_IN = 0.45359237, 2.54

# ---------------------------------------------------------------- master drug data
DRUGS = [  # iri-suffix, name, class, area, stage, preclinical id, clinical id (ph1/2), public id (ph3)
    ("DRG-0001", "Zorvantil", "JAK inhibitor", "Immunology", "Phase 3", "PC-ZV-0417", "CD-48213", "zorvantinib"),
    ("DRG-0002", "Oncotra", "Kinase inhibitor", "Oncology", "Phase 3", "PC-ON-0233", "CD-51877", "oncotrabine"),
    ("DRG-0003", "Cardiprex", "SGLT2 inhibitor", "Cardiometabolic", "Phase 3", "PC-CP-0098", "CD-60022", "cardiprexol"),
    ("DRG-0004", "Neurolynt", "Anti-amyloid antibody", "Neurology", "Phase 1", "PC-NL-0571", "CD-70419", None),
    ("DRG-0005", "Vexalin", "GLP-1 agonist", "Cardiometabolic", "Preclinical", "PC-VX-0820", None, None),
]
IRI = "http://example.org/pharma/drug/"
DRUG = {d[1]: d for d in DRUGS}

# id, acronym, title, phase, status, drug, n enrolled, site countries, first subject in, BMI mean, BMI sd
HUMAN = [
    ("CS-101", "ZOR-SAD", "Single ascending dose study of Zorvantil in healthy volunteers", 1, "Completed", "Zorvantil", 24, ["US"], date(2019, 3, 11), 27.5, 4.0),
    ("CS-102", "ZOR-RA2", "Phase 2 dose-ranging study of Zorvantil in rheumatoid arthritis", 2, "Completed", "Zorvantil", 60, ["GB", "DE", "FR", "PL"], date(2020, 6, 22), 27.0, 4.5),
    ("CS-103", "ZOR-RA3", "Phase 3 efficacy and safety study of Zorvantil in rheumatoid arthritis", 3, "Ongoing", "Zorvantil", 150, ["US", "US", "GB", "DE", "ES"], date(2022, 1, 17), 29.0, 5.0),
    ("CS-201", "ONC-XT2", "Phase 2 study of Oncotra in non-small cell lung cancer", 2, "Completed", "Oncotra", 50, ["US"], date(2021, 2, 8), 28.0, 5.0),
    ("CS-202", "ONC-XT3", "Phase 3 study of Oncotra versus standard of care in NSCLC", 3, "Ongoing", "Oncotra", 100, ["US", "GB", "DE", "FR"], date(2023, 5, 2), 27.5, 5.0),
    ("CS-301", "CARD-HF3", "Phase 3 cardiovascular outcomes study of Cardiprex in heart failure", 3, "Completed", "Cardiprex", 140, ["US", "US", "DE", "GB", "FR", "PL"], date(2021, 9, 13), 31.0, 5.5),
    ("CS-401", "NEURO-AD1", "Phase 1 safety study of Neurolynt in early Alzheimer's disease", 1, "Terminated", "Neurolynt", 20, ["GB", "DE"], date(2024, 2, 19), 26.0, 4.0),
]
INVIVO = [  # id, drug, species, strain, n animals, route, doses mg/kg (low, high), start
    ("IV-001", "Zorvantil", "RAT", "SPRAGUE-DAWLEY", 40, "ORAL", (10, 50), date(2016, 9, 5)),
    ("IV-002", "Oncotra", "MOUSE", "NOD-SCID", 30, "ORAL", (25, 100), date(2017, 11, 6)),
    ("IV-003", "Cardiprex", "RAT", "WISTAR", 40, "ORAL", (5, 30), date(2018, 2, 12)),
    ("IV-004", "Neurolynt", "DOG", "BEAGLE", 16, "INTRAVENOUS", (10, 40), date(2019, 7, 1)),
    ("IV-005", "Zorvantil", "MOUSE", "C57BL/6", 30, "ORAL", (15, 60), date(2017, 3, 20)),
    ("IV-006", "Vexalin", "RAT", "SPRAGUE-DAWLEY", 30, "SUBCUTANEOUS", (0.5, 2), date(2023, 4, 10)),
]
BASE_W = {"RAT": 220, "MOUSE": 22, "DOG": 9500}  # grams
SITES = {"US": ["101", "102", "103"], "GB": ["201", "202"], "DE": ["301", "302"], "FR": ["401"], "PL": ["501"], "ES": ["601"]}
AE_TERMS = [("Headache", "Nervous system disorders"), ("Nausea", "Gastrointestinal disorders"),
            ("Fatigue", "General disorders and administration site conditions"),
            ("Upper respiratory tract infection", "Infections and infestations"),
            ("Diarrhoea", "Gastrointestinal disorders"), ("Dizziness", "Nervous system disorders"),
            ("Rash", "Skin and subcutaneous tissue disorders"), ("Neutropenia", "Blood and lymphatic system disorders"),
            ("Alanine aminotransferase increased", "Investigations"), ("Hypertension", "Vascular disorders")]


def iso(d):
    return d.isoformat() if d else ""


def dt(d, delta):
    return d + timedelta(days=delta)


H = {k: [] for k in ["dm", "ex", "vs", "ae", "lb", "ds"]}
A = {k: [] for k in ["dm", "ex", "bw", "lb", "cl"]}
truth = {"human": {}, "animal": {}}


def human_study(sid, acr, title, phase, status, drug, n, countries, fsi, bmi_mu, bmi_sd):
    d = DRUG[drug]
    trt_id = d[6] if phase in (1, 2) else d[7]  # lifecycle-dependent drug id used in EX.EXTRT
    arms = [("PBO", "Placebo", "PLACEBO", 0)]
    arms += [("LOW", f"{drug} low dose", trt_id, 10), ("HIGH", f"{drug} high dose", trt_id, 40)] if phase > 1 else [("HIGH", f"{drug} single dose", trt_id, 40)]
    st = truth["human"].setdefault(sid, dict(patients=0, bmi_gt30=0, bmis=[], sae=0, disc=0, wts=[], drug=drug, drug_id=trt_id,
                                             alt3x=set(), gt30_by_country={}, acronym=acr, status=status, phase=phase))
    total = n + max(1, round(n * 0.08))  # plus screen failures
    enrol_end = TODAY if sid == "CS-202" else dt(fsi, 400 if status == "Ongoing" else 120 + n)
    dates = sorted(dt(fsi, R.randint(0, (enrol_end - fsi).days)) for _ in range(n))
    dates[0] = fsi
    for i in range(total):
        scr = i >= n
        cc = countries[i % len(countries)]
        site = SITES[cc][(i // len(countries)) % len(SITES[cc])]
        sex = R.choice("MF")
        usubjid = f"{sid}-{site}-{i + 1:04d}"
        rf = dates[i] if not scr else dt(fsi, R.randint(0, 300))
        arm = ("SCRNFAIL", "Screen Failure") if scr else R.choice(arms)[:2]
        H["dm"].append(dict(STUDYID=sid, DOMAIN="DM", USUBJID=usubjid, SUBJID=f"{i + 1:04d}", SITEID=site, COUNTRY=cc,
                            AGE=int(min(85, max(18, R.gauss(58 if phase > 1 else 36, 12)))), AGEU="YEARS", SEX=sex,
                            RACE=R.choice(["WHITE", "WHITE", "BLACK OR AFRICAN AMERICAN", "ASIAN", "OTHER"]), ETHNIC="NOT HISPANIC OR LATINO",
                            ARMCD=arm[0], ARM=arm[1], RFSTDTC="" if scr else iso(rf),
                            RFENDTC="" if (scr or status == "Ongoing") else iso(dt(rf, R.randint(84, 170)))))
        us = cc == "US"
        for _ in range(50):  # pick height/weight whose recorded BMI is not borderline at 30
            bmi = R.gauss(bmi_mu + (1.0 if us else 0), bmi_sd)
            h_cm = R.gauss(176 if sex == "M" else 163, 7)
            kg = bmi * (h_cm / 100) ** 2
            if us:
                h_rec, h_u, w_rec, w_u = round(h_cm / CM_PER_IN), "in", round(kg / KG_PER_LB), "lb"
                h_cm_r, w_kg_r = h_rec * CM_PER_IN, w_rec * KG_PER_LB
            elif R.random() < 0.15:
                h_rec, h_u, w_rec, w_u = round(h_cm / 100, 2), "m", round(kg, 1), "kg"
                h_cm_r, w_kg_r = h_rec * 100, w_rec
            else:
                h_rec, h_u, w_rec, w_u = round(h_cm), "cm", round(kg, 1), "kg"
                h_cm_r, w_kg_r = float(h_rec), w_rec
            bmi_r = w_kg_r / ((h_cm_r / 100) ** 2)
            if abs(bmi_r - 30) > 0.05:
                break
        no_height = (not scr) and R.random() < 0.03

        def vsrow(seq, code, name, res, unit, visit, vnum, base, day, not_done=False):
            row = dict(STUDYID=sid, DOMAIN="VS", USUBJID=usubjid, VSSEQ=seq, VSTESTCD=code, VSTEST=name,
                       VSORRES="" if not_done else res, VSORRESU="" if not_done else unit, VSSTRESC="", VSSTRESN="", VSSTRESU="",
                       VSBLFL="Y" if base else "", VISITNUM=vnum, VISIT=visit, VSDTC=iso(dt(rf, day)), VSSTAT="NOT DONE" if not_done else "")
            if not us and not not_done and code in ("HEIGHT", "WEIGHT"):  # standardised values only supplied by the EU CRO
                v = float(res) * ({"cm": 1, "m": 100}[unit] if code == "HEIGHT" else 1)
                row.update(VSSTRESC=f"{v:.2f}", VSSTRESN=round(v, 2), VSSTRESU="cm" if code == "HEIGHT" else "kg")
            H["vs"].append(row)

        if scr:
            vsrow(1, "HEIGHT", "Height", h_rec, h_u, "SCREENING", 1, False, -14)
            vsrow(2, "WEIGHT", "Weight", w_rec, w_u, "SCREENING", 1, False, -14)
            continue
        vsrow(1, "HEIGHT", "Height", h_rec, h_u, "BASELINE", 2, True, 0, no_height)
        vsrow(2, "WEIGHT", "Weight", w_rec, w_u, "BASELINE", 2, True, 0)
        vsrow(3, "SYSBP", "Systolic Blood Pressure", int(R.gauss(128, 12)), "mmHg", "BASELINE", 2, True, 0)
        vsrow(4, "DIABP", "Diastolic Blood Pressure", int(R.gauss(80, 8)), "mmHg", "BASELINE", 2, True, 0)
        w12 = w_rec * (1 + R.gauss(-0.01, 0.02))
        vsrow(5, "WEIGHT", "Weight", round(w12) if us else round(w12, 1), w_u, "WEEK 12", 5, False, 84)
        st["patients"] += 1
        if not no_height:
            st["bmis"].append(bmi_r)
            st["wts"].append(w_kg_r)
            if bmi_r > 30:
                st["bmi_gt30"] += 1
                st["gt30_by_country"][cc] = st["gt30_by_country"].get(cc, 0) + 1
        a = [x for x in arms if x[0] == arm[0]][0]
        H["ex"].append(dict(STUDYID=sid, DOMAIN="EX", USUBJID=usubjid, EXSEQ=1, EXTRT=a[2], EXDOSE=a[3], EXDOSU="mg",
                            EXDOSFRM="INJECTION" if drug == "Neurolynt" else "TABLET", EXROUTE="INTRAVENOUS" if drug == "Neurolynt" else "ORAL",
                            EXSTDTC=iso(rf), EXENDTC="" if status == "Ongoing" else iso(dt(rf, 84))))
        for k in range(R.choice([0, 0, 1, 1, 2, 3])):
            term, soc = R.choice(AE_TERMS)
            ser = "Y" if R.random() < 0.07 else "N"
            st["sae"] += ser == "Y"
            H["ae"].append(dict(STUDYID=sid, DOMAIN="AE", USUBJID=usubjid, AESEQ=k + 1, AETERM=term.upper(), AEDECOD=term, AEBODSYS=soc,
                                AESEV=R.choice(["MILD", "MILD", "MODERATE", "SEVERE"]), AESER=ser, AEREL=R.choice(["RELATED", "NOT RELATED"]),
                                AESTDTC=iso(dt(rf, R.randint(1, 80))), AEENDTC=iso(dt(rf, R.randint(81, 100))),
                                AEOUT=R.choice(["RECOVERED/RESOLVED", "RECOVERING/RESOLVING", "NOT RECOVERED/NOT RESOLVED"])))
        for visit, vnum, day in (("BASELINE", 2, 0), ("WEEK 12", 5, 84)):
            alt = max(8.0, R.gauss(24, 8))
            if drug == "Zorvantil" and a[3] == 40 and visit == "WEEK 12" and R.random() < 0.25:
                alt = R.uniform(125, 260)
            cr = round(max(40.0, R.gauss(80, 15)), 1)  # umol/L
            cr_us = round(cr / 88.4, 2)
            rows = (("ALT", "Alanine Aminotransferase", round(alt, 1), "U/L", round(alt, 1), 7, 40),
                    ("CREAT", "Creatinine", cr_us if us else cr, "mg/dL" if us else "umol/L", round(cr_us * 88.4, 1) if us else cr, 53, 106))
            for code, nm, res, unit, std, lo, hi in rows:
                H["lb"].append(dict(STUDYID=sid, DOMAIN="LB", USUBJID=usubjid, LBSEQ=len(H["lb"]) + 1, LBTESTCD=code, LBTEST=nm, LBORRES=res,
                                    LBORRESU=unit, LBSTRESN=std, LBSTRESU="U/L" if code == "ALT" else "umol/L", LBNRLO=lo, LBNRHI=hi,
                                    VISITNUM=vnum, VISIT=visit, LBDTC=iso(dt(rf, day))))
                if code == "ALT" and a[2] != "PLACEBO" and std > 3 * hi:
                    st["alt3x"].add(usubjid)
        if status != "Ongoing" or R.random() < 0.4:
            dec = "COMPLETED" if R.random() < 0.8 else R.choice(["ADVERSE EVENT", "WITHDRAWAL BY SUBJECT", "LOST TO FOLLOW-UP"])
            if status == "Terminated" and R.random() < 0.6:
                dec = "STUDY TERMINATED BY SPONSOR"
            st["disc"] += dec != "COMPLETED"
            H["ds"].append(dict(STUDYID=sid, DOMAIN="DS", USUBJID=usubjid, DSSEQ=1, DSTERM=dec, DSDECOD=dec, DSCAT="DISPOSITION EVENT",
                                DSSTDTC=iso(dt(rf, R.randint(84, 170)))))
        st.setdefault("rf", []).append(rf)
    st["fsi"], st["lsi"] = min(st["rf"]), max(st["rf"])


def invivo_study(sid, drug, species, strain, n, route, doses, start):
    d = DRUG[drug]
    arms = [("VEH", "Vehicle control", "VEHICLE", 0), ("LOW", "Low dose", d[5], doses[0]), ("HIGH", "High dose", d[5], doses[1])]
    st = truth["animal"].setdefault(sid, dict(animals=0, males=0, bw=[], drug=drug, species=species))
    for i in range(n):
        sex = "M" if i % 2 == 0 else "F"
        usubjid = f"{sid}-{i + 1:03d}"
        arm = arms[i % 3]
        A["dm"].append(dict(STUDYID=sid, DOMAIN="DM", USUBJID=usubjid, SUBJID=f"{i + 1:03d}", SPECIES=species, STRAIN=strain, SEX=sex,
                            AGE={"RAT": 8, "MOUSE": 7, "DOG": 26}[species], AGEU="WEEKS", ARMCD=arm[0], ARM=arm[1], SETCD=arm[0], RFSTDTC=iso(start)))
        A["ex"].append(dict(STUDYID=sid, DOMAIN="EX", USUBJID=usubjid, EXSEQ=1, EXTRT=arm[2], EXDOSE=arm[3], EXDOSU="mg/kg",
                            EXDOSFRM="SOLUTION", EXROUTE=route, EXSTDTC=iso(start), EXENDTC=iso(dt(start, 27))))
        bw0 = R.gauss(BASE_W[species] * (1.2 if sex == "M" else 1.0), BASE_W[species] * 0.06)
        st["animals"] += 1
        st["males"] += sex == "M"
        for day in (1, 14, 28):
            w = round(bw0 * (1 + 0.012 * (day - 1) * (0.5 if species == "DOG" else 1)), 1)
            A["bw"].append(dict(STUDYID=sid, DOMAIN="BW", USUBJID=usubjid, BWSEQ=len(A["bw"]) + 1, BWTESTCD="BW", BWTEST="Body Weight",
                                BWORRES=w, BWORRESU="g", BWSTRESN=w, BWSTRESU="g", BWDY=day, BWDTC=iso(dt(start, day - 1))))
            if day == 1:
                st["bw"].append(w)
        for code, nm, res, unit, lo, hi in (("ALT", "Alanine Aminotransferase", round(max(10, R.gauss(45, 12)), 1), "U/L", 20, 80),
                                            ("CREAT", "Creatinine", round(max(0.2, R.gauss(0.5, 0.1)), 2), "mg/dL", 0.2, 0.8)):
            A["lb"].append(dict(STUDYID=sid, DOMAIN="LB", USUBJID=usubjid, LBSEQ=len(A["lb"]) + 1, LBTESTCD=code, LBTEST=nm, LBORRES=res,
                                LBORRESU=unit, LBSTRESN=res, LBSTRESU=unit, LBNRLO=lo, LBNRHI=hi, VISITNUM=99, VISIT="TERMINAL SACRIFICE", LBDTC=iso(dt(start, 27))))
        if R.random() < 0.3:
            obs = R.choice(["PILOERECTION", "HYPOACTIVITY", "SALIVATION", "NORMAL"])
            A["cl"].append(dict(STUDYID=sid, DOMAIN="CL", USUBJID=usubjid, CLSEQ=len(A["cl"]) + 1, CLTESTCD="CLOBS", CLTEST="Clinical Observations",
                                CLORRES=obs, CLSTRESC=obs, CLDY=R.randint(1, 28), CLDTC=iso(dt(start, R.randint(0, 27)))))


for h in HUMAN:
    human_study(*h)
for v in INVIVO:
    invivo_study(*v)

# ---------------------------------------------------------------- USDM + master
USDM_STUDY, USDM_MS = [], []
for sid, acr, title, phase, status, drug, n, countries, fsi, *_ in HUMAN:
    t = truth["human"][sid]
    regions = "US" if set(countries) == {"US"} else ("EU" if "US" not in countries else "GLOBAL")
    USDM_STUDY.append(dict(STUDY_ID=sid, STUDY_ACRONYM=acr, STUDY_TITLE=title, STUDY_PHASE=f"Phase {phase}", STUDY_STATUS=status,
                           THERAPEUTIC_AREA=DRUG[drug][3], PLANNED_ENROLLMENT=n, STUDY_REGION=regions))
    planned_fsi = fsi - timedelta(days=R.randint(-14, 45))
    actual = {"FSI": t["fsi"], "LSI": t["lsi"] if sid != "CS-202" else None,
              "LSLV": dt(t["lsi"], 170) if status in ("Completed", "Terminated") else None,
              "DBL": dt(t["lsi"], 215) if status == "Completed" else None}
    off = {"FSI": 0, "LSI": 150, "LSLV": 320, "DBL": 360}
    names = {"FSI": "First Subject In", "LSI": "Last Subject In", "LSLV": "Last Subject Last Visit", "DBL": "Database Lock"}
    for code in ("FSI", "LSI", "LSLV", "DBL"):
        planned = dt(planned_fsi, off[code] + (R.randint(-20, 60) if code != "FSI" else 0))
        USDM_MS.append(dict(STUDY_ID=sid, MILESTONE_CODE=code, MILESTONE_NAME=names[code], PLANNED_DATE=iso(planned), ACTUAL_DATE=iso(actual[code])))
        if code == "LSI":
            t["lsi_late"] = bool(actual[code]) and actual[code] > planned
    t["fsi_year"] = t["fsi"].year

M_DRUG = [dict(DRUG_IRI=IRI + d[0], DRUG_NAME=d[1], DRUG_CLASS=d[2], THERAPEUTIC_AREA=d[3], LIFECYCLE_STAGE=d[4]) for d in DRUGS]
M_ID = [dict(DRUG_IRI=IRI + d[0], ID_SCHEME=s, ID_VALUE=v, VALID_FROM=f, VALID_TO="")
        for d in DRUGS for s, v, f in (("PRECLINICAL", d[5], "2015-01-01"), ("CLINICAL_PH12", d[6], "2018-06-01"), ("PUBLIC_PH3", d[7], "2021-01-01")) if v]

# ---------------------------------------------------------------- write scenarios
SDTM_T = {k: v for k, v in H.items()}
SEND_T = {k: v for k, v in A.items()}
COMMON = {"master": {"master_drug": M_DRUG, "master_drug_identifier": M_ID}, "usdm": {"usdm_study": USDM_STUDY, "usdm_study_milestone": USDM_MS}}


def build(scn):
    out = {}
    if scn == "s1":
        for sid, *_ in HUMAN:
            out[f"s1_sdtm_{sid.lower().replace('-', '')}"] = ("sdtm", {t: [r for r in rows if r["STUDYID"] == sid] for t, rows in SDTM_T.items()})
        for sid, *_ in INVIVO:
            out[f"s1_send_{sid.lower().replace('-', '')}"] = ("send", {t: [r for r in rows if r["STUDYID"] == sid] for t, rows in SEND_T.items()})
    else:
        out["s2_sdtm"], out["s2_send"] = ("sdtm", SDTM_T), ("send", SEND_T)
    for db, tabs in COMMON.items():
        out[f"{scn}_{db}"] = ("common", tabs)
    return out


schema, root = {}, HERE / "data"
shutil.rmtree(root, ignore_errors=True)
for scn, folder in (("s1", "scenario1_separate"), ("s2", "scenario2_combined")):
    schema[folder] = {}
    for db, (kind, tabs) in build(scn).items():
        schema[folder][db] = {}
        for t, rows in tabs.items():
            if not rows:
                continue
            cols = list((SDTM_T if kind == "sdtm" else SEND_T if kind == "send" else tabs)[t][0].keys())
            p = root / folder / db
            p.mkdir(parents=True, exist_ok=True)
            with open(p / f"{t}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                w.writerows(rows)
            schema[folder][db][t] = cols
(HERE / "schema.json").write_text(json.dumps(schema, indent=1))


# ---------------------------------------------------------------- expected answers
def drug_for(trt):
    return next((d[1] for d in DRUGS if trt in (d[5], d[6], d[7])), None)


hs, an = truth["human"], truth["animal"]
per_drug_h, per_drug_a = {}, {}
for rows, acc in ((H["ex"], per_drug_h), (A["ex"], per_drug_a)):
    for r in rows:
        dn = drug_for(r["EXTRT"])
        if dn:
            acc[dn] = acc.get(dn, 0) + 1
alt = {}
for t in hs.values():
    alt[t["drug"]] = alt.get(t["drug"], 0) + len(t["alt3x"])
expected = {
    "_note": "Computed from the generated rows; identical for scenario 1 and 2. 'patients' = DM rows with ARMCD != 'SCRNFAIL' (screen failures excluded). Placebo/vehicle subjects are not attributed to a drug in per-drug counts.",
    "bmi_definition": "baseline (VSBLFL='Y') weight kg / (height m)^2; in x 2.54 = cm, m x 100 = cm, lb x 0.45359237 = kg; patients without baseline height excluded",
    "q_bmi_over_30": [dict(study_id=s, study_acronym=t["acronym"], patients=t["bmi_gt30"], drug_name=t["drug"], drug_id=t["drug_id"],
                           study_status=t["status"], first_subject_in_year=t["fsi_year"]) for s, t in hs.items()],
    "total_patients_bmi_over_30": sum(t["bmi_gt30"] for t in hs.values()),
    "patients_bmi_over_30_by_country": {c: sum(t["gt30_by_country"].get(c, 0) for t in hs.values()) for c in sorted(SITES)},
    "total_patients_enrolled": sum(t["patients"] for t in hs.values()),
    "patients_per_study": {s: t["patients"] for s, t in hs.items()},
    "screen_failures": sum(r["ARMCD"] == "SCRNFAIL" for r in H["dm"]),
    "total_animals": len(A["dm"]),
    "animals_per_study": {s: t["animals"] for s, t in an.items()},
    "male_animals_per_species": {sp: sum(t["males"] for t in an.values() if t["species"] == sp) for sp in ("RAT", "MOUSE", "DOG")},
    "mean_baseline_bmi_per_study": {s: round(sum(t["bmis"]) / len(t["bmis"]), 2) for s, t in hs.items()},
    "mean_baseline_weight_kg_per_study": {s: round(sum(t["wts"]) / len(t["wts"]), 1) for s, t in hs.items()},
    "mean_day1_body_weight_g_per_study": {s: round(sum(t["bw"]) / len(t["bw"]), 1) for s, t in an.items()},
    "treated_patients_per_drug": per_drug_h,
    "treated_animals_per_drug": per_drug_a,
    "zorvantil_exposure_split": {"patients": per_drug_h.get("Zorvantil", 0), "animals": per_drug_a.get("Zorvantil", 0)},
    "serious_aes_per_study_acronym": {t["acronym"]: t["sae"] for t in hs.values()},
    "serious_aes_total": sum(t["sae"] for t in hs.values()),
    "discontinued_patients_per_study_acronym": {t["acronym"]: t["disc"] for t in hs.values()},
    "ongoing_studies_fsi_year": {t["acronym"]: t["fsi_year"] for t in hs.values() if t["status"] == "Ongoing"},
    "ongoing_study_count": sum(t["status"] == "Ongoing" for t in hs.values()),
    "studies_lsi_later_than_planned": sorted(s for s, t in hs.items() if t["lsi_late"]),
    "patients_alt_over_3xuln_active_arms_per_drug": alt,
    "drug_identifiers": {d[1]: {"PRECLINICAL": d[5], "CLINICAL_PH12": d[6], "PUBLIC_PH3": d[7]} for d in DRUGS},
    "drugs_with_both_invivo_and_clinical": sorted({t["drug"] for t in an.values()} & {t["drug"] for t in hs.values()}),
    "drugs_invivo_only": sorted({t["drug"] for t in an.values()} - {t["drug"] for t in hs.values()}),
    "completed_phase3_fsi_before_2022": [dict(study_id=s, acronym=t["acronym"], patients=t["patients"]) for s, t in hs.items()
                                         if t["phase"] == 3 and t["status"] == "Completed" and t["fsi_year"] < 2022],
}
(HERE / "expected_answers.json").write_text(json.dumps(expected, indent=1))

# ---------------------------------------------------------------- metrics
BMI_CTE = ("WITH b AS (SELECT usubjid, MAX(CASE WHEN vstestcd='HEIGHT' THEN TRY_CAST(NULLIF(vsorres,'') AS double) * "
           "CASE vsorresu WHEN 'in' THEN 2.54 WHEN 'cm' THEN 1 WHEN 'm' THEN 100 END END) AS h_cm, "
           "MAX(CASE WHEN vstestcd='WEIGHT' THEN TRY_CAST(NULLIF(vsorres,'') AS double) * "
           "CASE vsorresu WHEN 'lb' THEN 0.45359237 WHEN 'kg' THEN 1 END END) AS w_kg "
           "FROM vs WHERE vsblfl='Y' AND vstestcd IN ('HEIGHT','WEIGHT') GROUP BY usubjid) ")
BMI_GT30 = BMI_CTE + "SELECT COUNT(*) AS patients_bmi_over_30 FROM b WHERE w_kg / ((h_cm/100) * (h_cm/100)) > 30"
ENROLLED = "SELECT COUNT(*) AS enrolled_patient_count FROM dm WHERE armcd <> 'SCRNFAIL'"


def metric(name, desc, table, sql, unit, ret, syn, ex, dsid):
    return dict(name=name, description=desc, dataSourceId=dsid, sourceTable=table, unit=unit, returnType=ret,
                expression={"dialects": [{"dialect": "TRINO", "expression": sql}]}, aiContext={"synonyms": syn, "examples": ex})


COMMON_M = [
    metric("ongoing_study_count", "Number of clinical studies whose USDM study status is 'Ongoing'.", "usdm_study",
           "SELECT COUNT(*) AS ongoing_study_count FROM usdm_study WHERE study_status = 'Ongoing'", "count", "integer",
           ["active studies", "running trials"], ["How many studies are ongoing?"], "REPLACE_WITH_USDM_SOURCE_ID"),
    metric("clinical_stage_drug_count", "Number of master-data drugs in a clinical phase (Phase 1-3).", "master_drug",
           "SELECT COUNT(*) AS clinical_stage_drug_count FROM master_drug WHERE lifecycle_stage LIKE 'Phase%'", "count", "integer",
           ["drugs in clinical development"], ["How many drugs are in clinical development?"], "REPLACE_WITH_MASTER_SOURCE_ID"),
]
S, V = "REPLACE_WITH_SDTM_SOURCE_ID", "REPLACE_WITH_SEND_SOURCE_ID"
S2 = [
    metric("enrolled_patient_count", "Human patients enrolled in clinical (SDTM) studies; excludes screen failures. Not animals.", "dm", ENROLLED,
           "count", "integer", ["number of patients", "enrolled subjects"], ["How many patients are enrolled?"], S),
    metric("patients_bmi_over_30", "Enrolled human patients with baseline BMI above 30 (height in/m/cm and weight lb/kg normalised).", "vs", BMI_GT30,
           "count", "integer", ["obese patients", "BMI > 30"], ["How many patients have a BMI over 30?"], S),
    metric("mean_baseline_bmi", "Mean baseline BMI of human patients (unit-normalised).", "vs",
           BMI_CTE + "SELECT ROUND(AVG(w_kg / ((h_cm/100) * (h_cm/100))), 2) AS mean_baseline_bmi FROM b", "kg/m2", "decimal",
           ["average BMI"], ["What is the mean baseline BMI?"], S),
    metric("serious_adverse_event_count", "Serious adverse events (AESER = 'Y') in clinical studies.", "ae",
           "SELECT COUNT(*) AS serious_adverse_event_count FROM ae WHERE aeser = 'Y'", "count", "integer", ["SAE count"],
           ["How many serious adverse events are there?"], S),
    metric("animal_count", "Animals in in-vivo (SEND) studies. Not human patients.", "dm", "SELECT COUNT(*) AS animal_count FROM dm",
           "count", "integer", ["number of animals"], ["How many animals are in the in vivo studies?"], V),
    metric("mean_day1_body_weight_g", "Mean Day-1 body weight (grams) of animals in SEND studies.", "bw",
           "SELECT ROUND(AVG(bwstresn), 1) AS mean_day1_body_weight_g FROM bw WHERE bwdy = 1", "g", "decimal",
           ["average animal weight"], ["What is the average animal body weight at day 1?"], V),
] + COMMON_M
S1 = []
for sid, *_ in HUMAN:
    key, ph = sid.lower().replace("-", "_"), f"REPLACE_WITH_S1_SDTM_{sid.replace('-', '')}_SOURCE_ID"
    S1 += [metric(f"patients_bmi_over_30_{key}", f"Baseline BMI > 30 patients in study {sid} (SDTM).", "vs", BMI_GT30, "count", "integer",
                  ["obese patients"], [f"How many patients in {sid} have BMI over 30?"], ph),
           metric(f"enrolled_patient_count_{key}", f"Enrolled patients (no screen failures) in study {sid}.", "dm", ENROLLED, "count", "integer",
                  ["patients"], [f"How many patients in {sid}?"], ph)]
note = "Request bodies for POST /namespaces/{ns}/metrics. Replace the REPLACE_WITH_* placeholders with the approved source ids."
(HERE / "metrics_s1.json").write_text(json.dumps({"_note": note, "metrics": S1 + COMMON_M}, indent=1))
(HERE / "metrics_s2.json").write_text(json.dumps({"_note": note, "metrics": S2}, indent=1))

print("scenario1 dbs:", len(schema["scenario1_separate"]), " scenario2 dbs:", len(schema["scenario2_combined"]))
print("human rows:", {k: len(v) for k, v in H.items()}, " animal rows:", {k: len(v) for k, v in A.items()})
print("BMI>30:", expected["total_patients_bmi_over_30"], " patients:", expected["total_patients_enrolled"], " animals:", expected["total_animals"])
