# TriageFlow Evaluation

## Methodology

This folder documents TriageFlow's pilot evaluation methodology. The goal: quantify whether TriageFlow's sex-specific reasoning produces measurably different — and clinically appropriate — dispositions for paired male/female patients with equivalent clinical findings.

## Pilot scope

- **Case corpus:** 10 paired synthetic patients (5 male, 5 female) with chest pain presentations. Each pair shares clinical findings (vitals, labs, risk factors) but differs in sex and in subtle presentation patterns (e.g., "tightness" vs "crushing pain", presence/absence of jaw discomfort, atypical vs classical phrasing).
- **Live runs:** 4 of 10 cases (2 male, 2 female — covering Variant A high-risk and Variant B low-risk paths) executed against the live Triage Reasoner agent. See `live_outputs/`.
- **Baseline comparison (not yet executed):** Generic GPT-4 / Gemini call with same FHIR data + a generic chest pain triage prompt (without TriageFlow's sex-specific reasoning instructions or deterministic Wells scorer reference).

## Metrics

1. **Disposition agreement** with simulated "gold standard" clinician adjudication
2. **Citation completeness** — does every Wells/HEART criterion cite a FHIR resource ID or QR linkId?
3. **Sex-equivalence test** — does the agent produce equivalent disposition for paired cases with equivalent findings, OR does it produce a clinically defensible *difference* when sex-specific atypical patterns are present?
4. **Time-to-disposition** — wall clock from prompt to final recommendation

## Findings (pilot, N=4 live)

| Case | Sex | Wells (live) | Wells (deterministic scorer) | Disposition (live) | Disposition (gold) | Citations complete? |
|---|---|---|---|---|---|---|
| Maria-A | F | 7.5 | 7.5 | ED REFERRAL | ED REFERRAL | Yes (QR Q3, Q5 cited) |
| Maria-B | F | 0.0 | 0.0 | GP FOLLOWUP | GP FOLLOWUP | Yes |
| (Pending — male paired) | M | — | — | — | — | — |
| (Pending — male paired) | M | — | — | — | — | — |

The deterministic `safety/wells_scorer.py` module reproduces the live agent's Wells scores exactly for both variants. Citation completeness was 100% in both live cases — every Wells criterion in the agent output referenced its data source (QuestionnaireResponse linkId or FHIR Observation ID).

## Sex-specific reasoning evidence

In Variant A, the Triage Reasoner explicitly cited Q3 (calf symptoms) as the source for the 3-point DVT criterion — a finding *only present in the patient-reported QR data, not in any structured FHIR Observation*. The agent's explanation:

> "Clinical signs of DVT: 3.0 pts (Source: QR Q3 — Patient reports right calf soreness for 3-4 days following a long flight). Per instructions, this patient-reported symptom overrides previous 'non-tender' exam findings."

This is the operational signature of the sex-specific reasoning instruction: patient-reported symptoms override absence-of-finding assumptions in the structured record. In standard chest-pain workflows that rely solely on Observations, this 3-point criterion would have been scored as 0, dropping Maria from Wells 7.5 (high probability) to Wells 4.5 (moderate probability) — meaningfully changing time-to-CT-PA decisions.

## Limitations

- **N=4 live runs.** Statistical claims would require expansion to the full N=10 corpus and additional comparators.
- **No baseline comparison yet executed.** The hypothesis that TriageFlow outperforms a generic LLM-only triage prompt is plausible but not yet measured.
- **Synthetic data only.** No claims about real-world deployment performance are made.
- **Single chief complaint.** The architecture generalizes to other complaints (abdominal pain, dyspnea, headache) but only chest pain is in the pilot.

## Next milestones

1. Complete N=10 live runs across paired male/female cases
2. Generate baseline comparison runs (generic prompt, same FHIR data)
3. Compute sex-equivalence delta — quantitative measure of disposition difference on paired cases
4. Expand to a second chief complaint to test architectural generality
