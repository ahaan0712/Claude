from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
ELIGIBILITY_VALUES={"ELIGIBLE","VERIFY","SKIP","CLOSED"}
FIT_TIERS={"STRONG MATCH","GOOD MATCH","ADJACENT","WEAK MATCH"}
RETRIEVAL_VALUES={"FULL","PARTIAL","TITLE_ONLY","BLOCKED","FAILED","CLOSED","NEEDS_PROVIDER_SETUP"}
SOURCE_CLASSES={"XLSX_TARGET","TARGET_DISCOVERY","SUPPLEMENTAL_TRACKER"}
MONITORING_STATUSES={"NOT_DUE","MONITOR_SOON","MONITOR_NOW","OPEN_MATCH_FOUND","OPEN_BUT_INELIGIBLE","OPEN_BUT_OFF_TARGET","CHECKED_NO_MATCH","RETRIEVAL_BLOCKED","RETRIEVAL_FAILED","NEEDS_RESEARCH"}
ROLE_FAMILIES={"DATA_ANALYTICS","DATA_SCIENCE","BUSINESS_INTELLIGENCE","BUSINESS_ANALYTICS","ADJACENT_ANALYTICS","OUT_OF_SCOPE"}
CALIBRATION_VALUES={"PRIOR_ONLY","CALIBRATED","INSUFFICIENT_DATA"}
CANONICAL_POSTING_FIELDS=["posting_id","canonical_company_id","target_program_ids","company","title","role_family","role_reason_code","location","country","source","source_class","canonical_apply_url","tracker_url","posting_date","deadline","internship_term","employment_type","full_description","required_qualifications","preferred_qualifications","graduation_window","skills_required","skills_preferred","retrieval_status","retrieval_provider","retrieval_timestamp","data_completeness","work_authorization_evidence","sponsorship_evidence","citizenship_evidence","clearance_evidence","export_control_evidence","eligibility_status","eligibility_confidence","eligibility_reason_codes","eligibility_evidence","evidence_source","missing_evidence","verification_action","fit_tier","fit_reasons","demonstrated_skills","listed_skills","inferred_transferable_skills","matched_resume_evidence","missing_qualifications","application_priority","calibration_status","calibrated_probability","verification_items","application_status"]
def now_iso(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def write_json(path,obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n",encoding="utf-8")
def default_posting():
    d={k:None for k in CANONICAL_POSTING_FIELDS}
    for k in ["target_program_ids","skills_required","skills_preferred","eligibility_reason_codes","eligibility_evidence","missing_evidence","fit_reasons","demonstrated_skills","listed_skills","inferred_transferable_skills","matched_resume_evidence","missing_qualifications","verification_items"]: d[k]=[]
    d.update(country="United States",source_class="TARGET_DISCOVERY",retrieval_status="TITLE_ONLY",eligibility_status="VERIFY",eligibility_confidence="LOW",evidence_source="POSTING",verification_action="Review posting manually",fit_tier="WEAK MATCH",application_priority="VERIFY FIRST",calibration_status="PRIOR_ONLY",calibrated_probability=None,application_status="")
    return d
def validate_posting(p):
    miss=[k for k in CANONICAL_POSTING_FIELDS if k not in p]
    if miss: raise ValueError(f"missing fields: {miss}")
    if p["eligibility_status"] not in ELIGIBILITY_VALUES: raise ValueError("bad eligibility")
    if p["fit_tier"] not in FIT_TIERS: raise ValueError("bad fit")
    if p["retrieval_status"] not in RETRIEVAL_VALUES: raise ValueError("bad retrieval")
    if p["source_class"] not in SOURCE_CLASSES: raise ValueError("bad source_class")
