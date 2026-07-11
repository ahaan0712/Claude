from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "index.html"
HTML = INDEX.read_text(encoding="utf-8")


def test_campaign_identity_and_required_views_present():
    assert "Campaign 27" in HTML
    assert "Personalized Summer 2027 Internship Intelligence" in HTML
    for label in ["Jobs", "Saved", "Applications", "Insights", "Profile"]:
        assert f">{label}<" in HTML


def test_required_filters_and_sort_options_present():
    for label in [
        "Apply Now",
        "High Priority",
        "Eligible",
        "Verify First",
        "Data Analyst",
        "Data Analytics",
        "Data Science",
        "Business Intelligence",
        "Business Analytics",
        "Fresh",
        "Saved",
        "Applied",
    ]:
        assert label in HTML
    for option in ["Recommended", "Newest", "Strongest Match", "Eligibility", "Company"]:
        assert f"<option>{option}</option>" in HTML


def test_local_storage_and_tracking_statuses_preserved():
    assert "localStorage" in HTML
    assert "ahaan-2027-application-status" in HTML
    for status in [
        "saved",
        "applied",
        "online_assessment",
        "recruiter_screen",
        "interview",
        "final_round",
        "rejected",
        "offer",
        "withdrawn",
    ]:
        assert status in HTML


def test_accuracy_disclaimer_avoids_fake_probabilities():
    assert "not guaranteed interview probabilities" in HTML
    assert "not an interview probability" in HTML
    assert "Company H‑1B history is context only" in HTML
