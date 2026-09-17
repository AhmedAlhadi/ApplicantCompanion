from app.dates import apply_career_dates, career_date_or_empty, normalize_career_date


def test_normalize_month_name_year():
    assert normalize_career_date("AUGUST 2013") == "2013-08"
    assert normalize_career_date("August 2013") == "2013-08"
    assert normalize_career_date("Aug 2013") == "2013-08"
    assert normalize_career_date("Aug. 2013") == "2013-08"
    assert normalize_career_date("January 2021") == "2021-01"


def test_normalize_iso_and_numeric():
    assert normalize_career_date("2013-08") == "2013-08"
    assert normalize_career_date("2013-08-15") == "2013-08"
    assert normalize_career_date("2013/08") == "2013-08"
    assert normalize_career_date("08/2013") == "2013-08"
    assert normalize_career_date("8-2013") == "2013-08"
    assert normalize_career_date("2013") == "2013"


def test_normalize_open_ended_and_empty():
    assert normalize_career_date("") is None
    assert normalize_career_date(None) is None
    assert normalize_career_date("Present") is None
    assert normalize_career_date("current") is None
    assert normalize_career_date("حتى الآن") is None


def test_normalize_arabic_month():
    assert normalize_career_date("أغسطس 2013") == "2013-08"
    assert normalize_career_date("يناير ٢٠٢١") == "2021-01"


def test_unparseable_values_are_dropped():
    assert normalize_career_date("sometime around the early 2010s") is None
    assert normalize_career_date("unknown timeframe") is None
    assert normalize_career_date("n/a") is None
    assert career_date_or_empty("AUGUST 2013") == "2013-08"
    assert career_date_or_empty("nonsense") == ""


def test_apply_career_dates_on_payload():
    payload = {
        "start_date": "AUGUST 2013",
        "end_date": "Present",
        "issue_date": "June 2020",
        "title": "BSc",
    }
    apply_career_dates(payload)
    assert payload["start_date"] == "2013-08"
    assert payload["end_date"] is None
    assert payload["issue_date"] == "2020-06"
    assert payload["title"] == "BSc"
