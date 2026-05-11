# TriageFlow

> Multi-agent clinical triage that reasons like a clinician — including the patterns of patients medicine has historically missed.

Built on Prompt Opinion's Agent-to-Agent (A2A) infrastructure for the **Agents Assemble: Healthcare AI Endgame** hackathon (May 2026). Track: A2A Agent.

## What it is

TriageFlow is a four-agent clinical workflow that reads patient FHIR data + patient-reported answers, applies validated risk scores with sex-specific clinical reasoning, and hands off to the right downstream specialist agent based on disposition.

| Agent | Role |
|---|---|
| **Triage Reasoner** | Entry point. Reads FHIR observations + QuestionnaireResponse data. Computes Wells PE and HEART scores. Recommends one of four dispositions. |
| **ED Handoff Coordinator** | Generates SBAR-format emergency department handoff packets with working diagnosis, urgency tier, and recommended ED workflow. |
| **Referral Letter Generator** | Generates formal specialist referral letters with a single-sentence Clinical Question and specific answerable questions for the consultant. |
| **Patient Education Generator** | Generates plain-language take-home content at 6th-8th grade reading level with explicit return-to-ED criteria. |

## Why it exists

Chest pain in women is the most-missed serious diagnosis in primary care. Women with PE are diagnosed later than men. Women with MI are more likely to be told it's anxiety. Perimenopausal women present with "atypical" symptoms — pressure, fatigue, breathlessness — that don't match the textbook male-pattern crushing chest pain. The result is a measurable gap in time-to-diagnosis along sex lines.

TriageFlow encodes sex-specific clinical reasoning into the triage layer: patient-reported symptoms from a QuestionnaireResponse override absence-of-finding assumptions in the structured FHIR record. The Wells "clinical signs of DVT" criterion fires on QR-reported calf soreness even when no Observation resource documents it. This is a workflow problem masquerading as a model bias problem, and the fix is architectural.

## The clinical case

Demo patient: Maria Elena Reyes, 47-year-old perimenopausal woman, chest pain workup. Two variants of patient-reported answers produce two completely different paths through the same four-agent system:

**Variant A (ED route):** Sharp pleuritic pain, right calf soreness 3-4 days, recent 15-hour flight, recent tooth extraction with bedrest, on combined OCPs. Triage Reasoner computes **Wells 7.5 (high probability)**, recommends ED, hands off to ED Handoff Coordinator. Output: SBAR packet for the receiving emergency physician with explicit perimenopausal atypical-presentation framing.

**Variant B (GP route):** Tightness rather than pleuritic pain, no calf symptoms, no immobility concerns, no clotting history. Triage Reasoner computes **Wells 0 (low probability)**, recommends GP follow-up, hands off to Patient Education Generator. Output: plain-language patient education content with specific return-to-ED criteria.

Same patient. Same architecture. Two paths. That is the value of agentic triage over a static decision tree.

## Safety substrate

TriageFlow is designed to be deployable, not just demoable.

### Deterministic clinical math

The Wells PE score and HEART score are computed by [`safety/wells_scorer.py`](safety/wells_scorer.py) — a deterministic Python module published in this repo. The LLM-based Triage Reasoner extracts structured evidence (calf signs boolean, recent surgery <4 weeks boolean, HR > 100 boolean, etc.) from FHIR observations and QR answers. The scorer computes the points. **No autonomous LLM arithmetic in the critical path.** The LLM extracts; the scorer scores.

The scorer also encodes a **safety floor** — a deterministic disposition policy that escalates to ED regardless of LLM opinion when any of the following are true:
- Wells score >6 (high PE probability)
- HEART score >6 (high MACE risk)
- Wells moderate + elevated D-dimer
- Clinical DVT signs present

Run the test suite:

```bash
python safety/wells_scorer.py
```

All three tests pass: Variant A produces Wells 7.5 + ED escalation, Variant B produces Wells 0 + GP follow-up, and the safety floor enforces ED escalation on isolated DVT signs.

### Audit substrate by default

Every TriageFlow output traces every claim to a FHIR resource ID or QuestionnaireResponse linkId. This is not a clinical readability feature — it is the audit substrate. A regulator, a malpractice attorney, or a clinical informaticist auditing a disposition decision can trace it from action back to source data within seconds.

Example from a live Triage Reasoner output:

> Clinical signs of DVT: 3.0 pts (Source: QR Q3 — patient reports right calf soreness for 3-4 days following a long flight).
> Immobilization >3 days or surgery <4 weeks: 1.5 pts (Source: QR Q5 — 15-hour direct flight 10 days ago).

The Wells score did not appear from an LLM black box. The LLM extracted structured evidence. The deterministic scorer computed the points. The audit trail shows both. No claim without provenance.

### Regulatory positioning

TriageFlow is designed to qualify as **non-device clinical decision support under FDA 21st Century Cures Act §3060**:

1. **Not analyzing medical images, signals, or patterns.** Consumes structured FHIR observations and QR data. No image analysis, no waveform interpretation.
2. **Displaying or analyzing clinical info.** The four agents display analyzed clinical information to support workflows.
3. **Intended for healthcare providers, not direct patient action.** Triage Reasoner, ED Handoff, and Referral Letter output content for clinicians. Patient Education output is subject to clinician approval before release to patient.
4. **Independent review enabled.** Every recommendation cites every input that drove it. A clinician can independently review the basis for any recommendation in seconds — by design.

Additional standards:
- **FHIR R4** — All patient data flows through FHIR-conformant resources
- **SMART-on-FHIR** — OAuth client_credentials with `system/Patient.read system/QuestionnaireResponse.write` (least-privilege scopes)
- **SHARP Extension** — Patient context propagation via Prompt Opinion's FHIR Context Extension
- **HIPAA-aware** — Synthetic data only; no PHI

### Clinician-in-the-loop architecture

Every TriageFlow agent emits output explicitly labelled as a draft:

- Triage Reasoner: `Status: DECISION-SUPPORT RECOMMENDATION — pending licensed clinician approval`
- ED Handoff Coordinator: `Status: HANDOFF DRAFT — pending licensed clinician sign-off before ED transfer`
- Referral Letter Generator: `Status: REFERRAL DRAFT — pending clinician sign-off before transmission to specialist`
- Patient Education Generator: `Status: PATIENT EDUCATION DRAFT — pending clinician approval before release to patient`

Human is not in the loop because we added a checkbox. The architecture assumes the clinician's final action.

## Architecture

```
                    Patient FHIR record + QuestionnaireResponse
                                      │
                                      ▼
                          ┌──────────────────────┐
                          │   Triage Reasoner    │
                          │  (Wells + HEART)     │
                          └──────────────────────┘
                                      │
                                      ▼
                             Disposition decision
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            ▼                         ▼                         ▼
    ┌───────────────┐         ┌───────────────┐         ┌───────────────┐
    │  ED Handoff   │         │   Referral    │         │    Patient    │
    │  Coordinator  │         │     Letter    │         │  Education    │
    │   (SBAR)      │         │  Generator    │         │  Generator    │
    └───────────────┘         └───────────────┘         └───────────────┘

A2A handoff with structured payload: patient ID, working diagnosis,
risk score, key findings. FHIR Context Extension propagates patient
context across the entire chain.
```

## Repo layout

```
triageflow/
├── README.md                          (this file)
├── LICENSE                            (Apache 2.0)
├── system_prompts/
│   ├── triage_reasoner.md
│   ├── ed_handoff_coordinator.md
│   ├── referral_letter_generator.md
│   └── patient_education_generator.md
├── fhir_bundles/
│   ├── maria_reyes_patient_bundle.json
│   └── questionnaire_responses.json
├── safety/
│   └── wells_scorer.py                (deterministic scorer + tests)
└── evaluation/
    ├── README.md                      (methodology + findings)
    ├── case_corpus.json               (paired test cases)
    └── live_outputs/                  (real agent outputs)
```

## Try it on Prompt Opinion

The four agents are published to the Prompt Opinion Marketplace. Search for "Triage Reasoner" (and its 3 downstream companions) at https://app.promptopinion.ai/marketplace.

## What's next

- Extend Triage Reasoner to additional chief complaints (abdominal pain, dyspnea, headache)
- Clinician feedback loop: capture which dispositions licensed clinicians override and why
- Outcome tracking: connect to follow-up data (was the PE actually confirmed? Did the referral go through?)
- Other underdiagnosed populations: elderly atypical sepsis, pediatric Kawasaki disease

## License

Apache 2.0. See [LICENSE](LICENSE).

## Author

Ankita Sahu / ZkAGI — Bhubaneswar, India.

Built for Agents Assemble: The Healthcare AI Endgame, May 2026.
