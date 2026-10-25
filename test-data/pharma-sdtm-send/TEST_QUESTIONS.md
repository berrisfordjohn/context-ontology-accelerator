# Test questions (pharma SDTM/SEND/USDM)

Same questions for scenario 1 and 2. Expected answers are computed in `expected_answers.json` (ground truth from the generator). Scenario 1 answers must combine multiple sources.

| # | Question | Expected |
|---|---|---|
| 1 | How many patients are enrolled across all clinical studies (excluding screen failures)? | 544 |
| 2 | How many animals are on in vivo studies? | 186 |
| 3 | Find the number of patients with a BMI over 30. Return the study id, study acronym, number of patients, drug name, drug id, status of the study and the year of first subject in. Heights and weights may be imperial (US) or metric. | CS-101 ZOR-SAD: 10 pts, Zorvantil, CD-48213, Completed, FSI 2019; CS-102 ZOR-RA2: 12 pts, Zorvantil, CD-48213, Completed, FSI 2020; CS-103 ZOR-RA3: 65 pts, Zorvantil, zorvantinib, Ongoing, FSI 2022; CS-201 ONC-XT2: 15 pts, Oncotra, CD-51877, Completed, FSI 2021; CS-202 ONC-XT3: 35 pts, Oncotra, oncotrabine, Ongoing, FSI 2023; CS-301 CARD-HF3: 84 pts, Cardiprex, cardiprexol, Completed, FSI 2021; CS-401 NEURO-AD1: 5 pts, Neurolynt, CD-70419, Terminated, FSI 2024 |
| 4 | In total, how many patients have a baseline BMI over 30? | 226 |
| 5 | How many patients with a baseline BMI over 30 are there per country? | DE=41; ES=14; FR=25; GB=31; PL=14; US=101 |
| 6 | How many enrolled patients are there per clinical study? | CS-101=24; CS-102=60; CS-103=150; CS-201=50; CS-202=100; CS-301=140; CS-401=20 |
| 7 | How many screen failures were there across clinical studies? | 44 |
| 8 | What is the mean baseline BMI per clinical study? | CS-101=29.56; CS-102=26.5; CS-103=29.11; CS-201=28.13; CS-202=27.88; CS-301=31.72; CS-401=26.08 |
| 9 | What is the mean baseline weight in kg per clinical study? | CS-101=84.7; CS-102=74.7; CS-103=83.2; CS-201=79.4; CS-202=80.4; CS-301=91.5; CS-401=73.6 |
| 10 | What is the mean day 1 body weight in grams per in vivo study? | IV-001=240.0; IV-002=24.9; IV-003=242.4; IV-004=10381.9; IV-005=23.7; IV-006=242.0 |
| 11 | How many patients were treated with each drug (by drug name, excluding placebo)? | Zorvantil=158; Oncotra=97; Cardiprex=95; Neurolynt=10 |
| 12 | How many animals were treated with each drug (by drug name, excluding vehicle)? | Zorvantil=46; Oncotra=20; Cardiprex=26; Neurolynt=10; Vexalin=20 |
| 13 | How many patients and how many animals were exposed to Zorvantil? | patients=158; animals=46 |
| 14 | How many serious adverse events were there per clinical study acronym? | ZOR-SAD=5; ZOR-RA2=4; ZOR-RA3=20; ONC-XT2=4; ONC-XT3=7; CARD-HF3=13; NEURO-AD1=2 |
| 15 | How many patients discontinued each clinical study (by acronym)? | ZOR-SAD=7; ZOR-RA2=15; ZOR-RA3=11; ONC-XT2=10; ONC-XT3=8; CARD-HF3=31; NEURO-AD1=16 |
| 16 | Which clinical studies are ongoing and in what year was first subject in? | ZOR-RA3=2022; ONC-XT3=2023 |
| 17 | Which clinical studies had last subject in later than planned? | CS-102, CS-103, CS-201, CS-301 |
| 18 | How many patients had ALT above 3 times the upper limit of normal, per drug, on active arms? | Zorvantil=34; Oncotra=0; Cardiprex=0; Neurolynt=0 |
| 19 | Which drugs have been used in both in vivo and clinical studies? | Cardiprex, Neurolynt, Oncotra, Zorvantil |
| 20 | Which drugs have only been used in in vivo studies? | Vexalin |
| 21 | How many male animals are there per species? | RAT=55; MOUSE=30; DOG=8 |
| 22 | Which completed phase 3 clinical studies had first subject in before 2022? Give study id, acronym and number of patients. | CS-301 CARD-HF3 140 |
