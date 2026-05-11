"""
TriageFlow — Deterministic Clinical Scorer
==========================================

Reference implementation of the Wells PE and HEART scores as deterministic
Python functions. Designed as the safety substrate for TriageFlow's
clinical reasoning agents.

ARCHITECTURAL CONTRACT
----------------------
The LLM-based Triage Reasoner agent extracts STRUCTURED EVIDENCE from
FHIR observations and patient-reported answers (QuestionnaireResponse).
This module then computes the SCORE deterministically. Clinical
arithmetic does not autonomously execute in an LLM in the production
critical path.

The LLM extracts. The scorer scores.

CLINICAL REFERENCES
-------------------
- Wells PE score: Wells et al., Thrombosis and Haemostasis 2000;83:416-420
- HEART score:    Six et al., Critical Pathways in Cardiology 2008
- PERC rule:      Kline et al., J Thromb Haemost 2004;2:1247-1255

This module is decision SUPPORT. Final clinical disposition rests with
the licensed clinician.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Wells PE Score
# ---------------------------------------------------------------------------

class WellsProbability(str, Enum):
    LOW = "low"            # <2.0
    MODERATE = "moderate"  # 2.0 - 6.0
    HIGH = "high"          # >6.0


@dataclass
class WellsEvidence:
    """
    Structured evidence extracted by the LLM from FHIR + QR data.

    Each field MUST be sourced. The `*_source` fields are FHIR Observation
    IDs or QuestionnaireResponse linkIds. They populate the audit trail.
    """
    # Criterion 1 — Clinical signs and symptoms of DVT (3.0 pts)
    dvt_signs: bool
    dvt_signs_source: str  # e.g. "QR/q3_calf_symptoms" or "Observation/<uuid>"

    # Criterion 2 — PE is #1 diagnosis or equally likely (3.0 pts)
    pe_primary_diagnosis: bool
    pe_primary_diagnosis_source: str

    # Criterion 3 — Heart rate > 100 bpm (1.5 pts)
    heart_rate_over_100: bool
    heart_rate_value: Optional[float]
    heart_rate_source: str

    # Criterion 4 — Immobilization >3 days OR surgery <4 weeks (1.5 pts)
    immobilization_or_recent_surgery: bool
    immobilization_or_recent_surgery_source: str

    # Criterion 5 — Previous PE or DVT (1.5 pts)
    previous_pe_or_dvt: bool
    previous_pe_or_dvt_source: str

    # Criterion 6 — Hemoptysis (1.0 pt)
    hemoptysis: bool
    hemoptysis_source: str

    # Criterion 7 — Malignancy on treatment or palliative (1.0 pt)
    malignancy_active: bool
    malignancy_active_source: str


@dataclass
class WellsScoreResult:
    score: float
    probability_tier: WellsProbability
    criteria_breakdown: list[dict] = field(default_factory=list)

    def to_audit_string(self) -> str:
        """Human-readable audit trail for clinician review."""
        lines = [
            f"Wells PE Score: {self.score} ({self.probability_tier.value} probability)",
            "Criterion-by-criterion breakdown:",
        ]
        for crit in self.criteria_breakdown:
            lines.append(
                f"  - {crit['name']}: {crit['points']} pts "
                f"({'TRUE' if crit['present'] else 'false'}) "
                f"[source: {crit['source']}]"
            )
        return "\n".join(lines)


def compute_wells_score(evidence: WellsEvidence) -> WellsScoreResult:
    """
    Deterministic Wells PE score computation.

    Returns the score, the probability tier, and a fully-cited audit trail.
    """
    criteria = [
        {
            "name": "Clinical signs and symptoms of DVT",
            "present": evidence.dvt_signs,
            "points": 3.0 if evidence.dvt_signs else 0.0,
            "source": evidence.dvt_signs_source,
        },
        {
            "name": "PE is #1 diagnosis or equally likely",
            "present": evidence.pe_primary_diagnosis,
            "points": 3.0 if evidence.pe_primary_diagnosis else 0.0,
            "source": evidence.pe_primary_diagnosis_source,
        },
        {
            "name": "Heart rate > 100 bpm",
            "present": evidence.heart_rate_over_100,
            "points": 1.5 if evidence.heart_rate_over_100 else 0.0,
            "source": evidence.heart_rate_source,
        },
        {
            "name": "Immobilization >3 days or surgery <4 weeks",
            "present": evidence.immobilization_or_recent_surgery,
            "points": 1.5 if evidence.immobilization_or_recent_surgery else 0.0,
            "source": evidence.immobilization_or_recent_surgery_source,
        },
        {
            "name": "Previous PE or DVT",
            "present": evidence.previous_pe_or_dvt,
            "points": 1.5 if evidence.previous_pe_or_dvt else 0.0,
            "source": evidence.previous_pe_or_dvt_source,
        },
        {
            "name": "Hemoptysis",
            "present": evidence.hemoptysis,
            "points": 1.0 if evidence.hemoptysis else 0.0,
            "source": evidence.hemoptysis_source,
        },
        {
            "name": "Malignancy on treatment or palliative",
            "present": evidence.malignancy_active,
            "points": 1.0 if evidence.malignancy_active else 0.0,
            "source": evidence.malignancy_active_source,
        },
    ]

    total = sum(c["points"] for c in criteria)

    if total < 2.0:
        tier = WellsProbability.LOW
    elif total <= 6.0:
        tier = WellsProbability.MODERATE
    else:
        tier = WellsProbability.HIGH

    return WellsScoreResult(
        score=total,
        probability_tier=tier,
        criteria_breakdown=criteria,
    )


# ---------------------------------------------------------------------------
# HEART Score
# ---------------------------------------------------------------------------

class HeartRisk(str, Enum):
    LOW = "low"                # 0-3
    MODERATE = "moderate"      # 4-6
    HIGH = "high"              # 7-10


@dataclass
class HeartEvidence:
    """
    Structured evidence for the HEART score, sourced to FHIR/QR.
    Each component is an int 0/1/2 per the validated HEART rubric.
    """
    history_score: int          # 0=slightly suspicious, 1=moderate, 2=highly
    history_source: str

    ecg_score: int              # 0=normal, 1=non-specific repolarization, 2=ST deviation
    ecg_source: str

    age_score: int              # 0=<45, 1=45-64, 2=>=65
    age_source: str

    risk_factors_count: int     # HTN, hypercholesterolemia, DM, obesity, smoker, FHx
    risk_factors_source: str

    troponin_score: int         # 0=normal, 1=1-3x normal, 2=>3x normal
    troponin_source: str

    def __post_init__(self):
        for label, value in [
            ("history", self.history_score),
            ("ecg", self.ecg_score),
            ("age", self.age_score),
            ("troponin", self.troponin_score),
        ]:
            if value not in (0, 1, 2):
                raise ValueError(f"{label}_score must be 0, 1, or 2; got {value}")


@dataclass
class HeartScoreResult:
    score: int
    risk_tier: HeartRisk
    criteria_breakdown: list[dict] = field(default_factory=list)

    def to_audit_string(self) -> str:
        lines = [
            f"HEART Score: {self.score} ({self.risk_tier.value} risk)",
            "Criterion-by-criterion breakdown:",
        ]
        for crit in self.criteria_breakdown:
            lines.append(
                f"  - {crit['name']}: {crit['points']} pts "
                f"[source: {crit['source']}]"
            )
        return "\n".join(lines)


def compute_heart_score(evidence: HeartEvidence) -> HeartScoreResult:
    """
    Deterministic HEART score for ED chest pain risk stratification.
    """
    # Risk factor scoring: 0 if no risk factors, 1 if 1-2, 2 if >=3 OR known atheroclerotic disease
    if evidence.risk_factors_count == 0:
        rf_points = 0
    elif evidence.risk_factors_count in (1, 2):
        rf_points = 1
    else:
        rf_points = 2

    criteria = [
        {"name": "History", "points": evidence.history_score, "source": evidence.history_source},
        {"name": "ECG", "points": evidence.ecg_score, "source": evidence.ecg_source},
        {"name": "Age", "points": evidence.age_score, "source": evidence.age_source},
        {"name": "Risk factors", "points": rf_points, "source": evidence.risk_factors_source},
        {"name": "Troponin", "points": evidence.troponin_score, "source": evidence.troponin_source},
    ]
    total = sum(c["points"] for c in criteria)

    if total <= 3:
        tier = HeartRisk.LOW
    elif total <= 6:
        tier = HeartRisk.MODERATE
    else:
        tier = HeartRisk.HIGH

    return HeartScoreResult(
        score=total,
        risk_tier=tier,
        criteria_breakdown=criteria,
    )


# ---------------------------------------------------------------------------
# Disposition policy
# ---------------------------------------------------------------------------

class Disposition(str, Enum):
    ED_REFERRAL = "ED_REFERRAL"
    SPECIALIST_REFERRAL = "SPECIALIST_REFERRAL"
    GP_FOLLOWUP = "GP_FOLLOWUP"
    DISCHARGE_WITH_SAFETYNET = "DISCHARGE_WITH_SAFETYNET"


def recommend_disposition(
    wells: WellsScoreResult,
    heart: HeartScoreResult,
    d_dimer_elevated: bool,
    has_dvt_signs: bool,
) -> tuple[Disposition, str]:
    """
    Deterministic disposition policy. Encodes the safety floor: any
    combination meeting these criteria escalates regardless of LLM opinion.

    Returns (disposition, rationale).
    """
    # ED escalation rules (any one triggers ED)
    if wells.probability_tier == WellsProbability.HIGH:
        return Disposition.ED_REFERRAL, "Wells score >6 (high PE probability) — CT-PA required"

    if heart.risk_tier == HeartRisk.HIGH:
        return Disposition.ED_REFERRAL, "HEART score >6 (high MACE risk) — serial troponins required"

    if wells.probability_tier == WellsProbability.MODERATE and d_dimer_elevated:
        return Disposition.ED_REFERRAL, "Wells moderate + elevated D-dimer — CT-PA required to rule out PE"

    if has_dvt_signs:
        return Disposition.ED_REFERRAL, "Clinical DVT signs present — lower extremity Doppler + PE workup required"

    # Specialist referral
    if heart.risk_tier == HeartRisk.MODERATE:
        return Disposition.SPECIALIST_REFERRAL, "HEART score 4-6 (moderate MACE risk) — outpatient cardiology evaluation"

    # GP follow-up
    if wells.probability_tier == WellsProbability.LOW and heart.risk_tier == HeartRisk.LOW:
        return Disposition.GP_FOLLOWUP, "Low Wells + low HEART — GP follow-up with safety-netting"

    # Fallback safety: when in doubt, escalate
    return Disposition.SPECIALIST_REFERRAL, "Ambiguous — defaulting to specialist review per safety floor"


# ---------------------------------------------------------------------------
# Unit tests (run with `python -m pytest wells_scorer.py` or just `python wells_scorer.py`)
# ---------------------------------------------------------------------------

def _test_variant_A_ed_route():
    """Maria Reyes Variant A (high-risk): expect Wells 7.5, HIGH, ED."""
    evidence = WellsEvidence(
        dvt_signs=True,
        dvt_signs_source="QR/q3_calf_symptoms",
        pe_primary_diagnosis=True,
        pe_primary_diagnosis_source="LLM-extracted clinical synthesis",
        heart_rate_over_100=False,
        heart_rate_value=96.0,
        heart_rate_source="Observation/78a974a8",
        immobilization_or_recent_surgery=True,
        immobilization_or_recent_surgery_source="QR/q5_recent_immobility",
        previous_pe_or_dvt=False,
        previous_pe_or_dvt_source="QR/q6_clotting_history",
        hemoptysis=False,
        hemoptysis_source="QR/q4_hemoptysis",
        malignancy_active=False,
        malignancy_active_source="Condition resource scan",
    )
    result = compute_wells_score(evidence)
    assert result.score == 7.5, f"Expected 7.5, got {result.score}"
    assert result.probability_tier == WellsProbability.HIGH

    heart = HeartEvidence(
        history_score=1, history_source="DocumentReference/intake",
        ecg_score=0, ecg_source="Observation/ecg",
        age_score=1, age_source="Patient/dob",
        risk_factors_count=2, risk_factors_source="Conditions + family history",
        troponin_score=0, troponin_source="Observation/troponin",
    )
    heart_result = compute_heart_score(heart)
    assert heart_result.score == 3, f"Expected HEART=3, got {heart_result.score}"

    disposition, rationale = recommend_disposition(
        result, heart_result, d_dimer_elevated=True, has_dvt_signs=True,
    )
    assert disposition == Disposition.ED_REFERRAL
    print(f"[PASS] Variant A: Wells {result.score}, HEART {heart_result.score}, {disposition.value}")
    print(f"       Rationale: {rationale}")


def _test_variant_B_gp_route():
    """Maria Reyes Variant B (low-risk): expect Wells 0, LOW, GP."""
    evidence = WellsEvidence(
        dvt_signs=False, dvt_signs_source="QR/q3_calf_symptoms",
        pe_primary_diagnosis=False, pe_primary_diagnosis_source="LLM clinical synthesis",
        heart_rate_over_100=False, heart_rate_value=96.0, heart_rate_source="Observation/hr",
        immobilization_or_recent_surgery=False, immobilization_or_recent_surgery_source="QR/q5",
        previous_pe_or_dvt=False, previous_pe_or_dvt_source="QR/q6",
        hemoptysis=False, hemoptysis_source="QR/q4",
        malignancy_active=False, malignancy_active_source="Conditions",
    )
    result = compute_wells_score(evidence)
    assert result.score == 0.0
    assert result.probability_tier == WellsProbability.LOW

    heart = HeartEvidence(
        history_score=1, history_source="intake",
        ecg_score=0, ecg_source="ecg",
        age_score=1, age_source="dob",
        risk_factors_count=2, risk_factors_source="conditions",
        troponin_score=0, troponin_source="trop",
    )
    heart_result = compute_heart_score(heart)
    disposition, rationale = recommend_disposition(
        result, heart_result, d_dimer_elevated=False, has_dvt_signs=False,
    )
    assert disposition == Disposition.GP_FOLLOWUP
    print(f"[PASS] Variant B: Wells {result.score}, HEART {heart_result.score}, {disposition.value}")
    print(f"       Rationale: {rationale}")


def _test_safety_floor():
    """Safety floor: clinical DVT signs MUST escalate to ED regardless of other inputs."""
    evidence = WellsEvidence(
        dvt_signs=True, dvt_signs_source="QR/q3",
        pe_primary_diagnosis=False, pe_primary_diagnosis_source="LLM",
        heart_rate_over_100=False, heart_rate_value=72.0, heart_rate_source="obs",
        immobilization_or_recent_surgery=False, immobilization_or_recent_surgery_source="QR",
        previous_pe_or_dvt=False, previous_pe_or_dvt_source="QR",
        hemoptysis=False, hemoptysis_source="QR",
        malignancy_active=False, malignancy_active_source="conditions",
    )
    result = compute_wells_score(evidence)  # Wells = 3.0, moderate
    heart = HeartEvidence(
        history_score=0, history_source="intake",
        ecg_score=0, ecg_source="ecg",
        age_score=0, age_source="dob",
        risk_factors_count=0, risk_factors_source="none",
        troponin_score=0, troponin_source="trop",
    )
    heart_result = compute_heart_score(heart)
    disposition, _ = recommend_disposition(
        result, heart_result, d_dimer_elevated=False, has_dvt_signs=True,
    )
    assert disposition == Disposition.ED_REFERRAL, "Safety floor violated: DVT signs must escalate"
    print(f"[PASS] Safety floor: DVT signs alone escalate to ED")


if __name__ == "__main__":
    print("Running TriageFlow deterministic scorer test suite...\n")
    _test_variant_A_ed_route()
    _test_variant_B_gp_route()
    _test_safety_floor()
    print("\nAll tests passed.")
