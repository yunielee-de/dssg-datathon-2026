"""Opening-hours parser. Inputs mirror real formats found in the pool (anonymised)."""

from datetime import datetime

import pytest

from fdp_mcp import hours
from fdp_mcp.hours import BERLIN

D = "MoDiMiDoFrSaSo"


def table(text):
    """{kind: {"Mo": "09:00-12:00,14:00-16:00", ...}}"""

    schedule = hours.parse(text)
    return {
        kind: {D[2 * d:2 * d + 2]: ",".join(f"{a:%H:%M}-{b:%H:%M}" for a, b in ivs) for d, ivs in sorted(per_day.items())}
        for kind, per_day in schedule.intervals.items()
    }


WEEK_9_12 = {d: "09:00-12:00" for d in ("Mo", "Di", "Mi", "Do", "Fr")}


@pytest.mark.parametrize("text, expected", [
    # Basic formats
    ("Montag bis Freitag 9.00 Uhr bis 12.00 Uhr", {"opening": WEEK_9_12}),
    ("Mo - Fr 9 - 12 Uhr", {"opening": WEEK_9_12}),
    ("MO-FR: 9:00 - 12:00", {"opening": WEEK_9_12}),
    ("mo - fr 09:00-12:00", {"opening": WEEK_9_12}),
    ("Werktäglich 9:00 bis 12:00 Uhr", {"opening": WEEK_9_12}),
    ("Mo 09:00-12:00;Tu 09:00-12:00;We 09:00-12:00;Th 09:00-12:00;Fr 09:00-12:00", {"opening": WEEK_9_12}),
    # Lists, chains, several groups, split days
    ("Mo, Mi & Fr 08:00 Uhr - 13:00 Uhr Di & Do 13:00 Uhr - 18:00 Uhr",
     {"opening": {"Mo": "08:00-13:00", "Di": "13:00-18:00", "Mi": "08:00-13:00", "Do": "13:00-18:00", "Fr": "08:00-13:00"}}),
    ("Mo. Di. Do. von 09.00 bis 12.30 Uhr",
     {"opening": {"Mo": "09:00-12:30", "Di": "09:00-12:30", "Do": "09:00-12:30"}}),
    ("Mo-Mi-Do 9:00-16:30 Uhr", {"opening": {"Mo": "09:00-16:30", "Mi": "09:00-16:30", "Do": "09:00-16:30"}}),
    ("Mo. + Di.:09:00 - 12:00 und 13:00 - 16:00",
     {"opening": {"Mo": "09:00-12:00,13:00-16:00", "Di": "09:00-12:00,13:00-16:00"}}),
    ("Mo - Fr 9-12 Uhr Mo - Do 14-16 Uhr",
     {"opening": {**{d: "09:00-12:00,14:00-16:00" for d in ("Mo", "Di", "Mi", "Do")}, "Fr": "09:00-12:00"}}),
    ("Sa - So 10-14 Uhr", {"opening": {"Sa": "10:00-14:00", "So": "10:00-14:00"}}),
    # Kinds of hours
    ("Telefonische Erreichbarkeit: Mo - Fr 9 - 12 Uhr Sprechstunde Di 14 - 16 Uhr",
     {"phone": WEEK_9_12, "consultation": {"Di": "14:00-16:00"}}),
    ("Tel. Sprechzeiten: Mo 9-12", {"phone": {"Mo": "09:00-12:00"}}),
    # Regressions found in the manual audit
    ("Montag 8: 00 bis 16:00 Uhr", {"opening": {"Mo": "08:00-16:00"}}),
    ("Mo - Fr 8.30 bis 12.30 Uhr und nachmittags, außer freitags 14-16 Uhr",
     {"opening": {**{d: "08:30-12:30,14:00-16:00" for d in ("Mo", "Di", "Mi", "Do")}, "Fr": "08:30-12:30"}}),
    ("Montag-Freitag 11:45 bis 17:00 Uhr in den Schulferien 7:30 bis 17:00 Uhr",
     {"opening": {d: "11:45-17:00" for d in ("Mo", "Di", "Mi", "Do", "Fr")},
      "holidays": {d: "07:30-17:00" for d in ("Mo", "Di", "Mi", "Do", "Fr")}}),
    ("Mo - Fr 8:00 - 19:00 Uhr Fr 8:00 - 17:00 Uhr",
     {"opening": {**{d: "08:00-19:00" for d in ("Mo", "Di", "Mi", "Do")}, "Fr": "08:00-17:00"}}),
    ("Mo ? Do 9:00 bis 12:00 Uhr", {"opening": {d: "09:00-12:00" for d in ("Mo", "Di", "Mi", "Do")}}),
    ("Dienstag 9:00-13:00 Mitwoch 14:00-19:00", {"opening": {"Di": "09:00-13:00", "Mi": "14:00-19:00"}}),
    ("Donnerstags 9-11 Uhr am 1. Freitag im Monat 17-19 Uhr", {"opening": {"Do": "09:00-11:00"}}),
    # Words that look like weekdays but are not
    ("Dienst-Handy: Mo-Fr 9-12 Uhr", {"opening": WEEK_9_12}),
    ("so ist es: Mo 9-12", {"opening": {"Mo": "09:00-12:00"}}),
])
def test_parse(text, expected):
    assert table(text) == expected


@pytest.mark.parametrize("text", ["0211/20992200", "Tel. 0341 12-34", "Haltestelle Linie 8 - 12"])
def test_phone_numbers_and_noise_are_not_hours(text):
    assert not hours.parse(text).parsed


def test_appointment_only_and_empty():
    assert hours.status_at(hours.parse("Termine nach Vereinbarung"), datetime.now(BERLIN))["status"] == "by_appointment"
    assert hours.status_at(hours.parse(None), datetime.now(BERLIN))["status"] == "unknown"


def test_times_without_days_are_reported_not_guessed():
    schedule = hours.parse("09:00 - 16:00 Uhr")
    assert not schedule.parsed and schedule.times_without_days == ["09:00-16:00"]


def test_partial_is_flagged():
    schedule = hours.parse("Mo 9-12 Uhr, außerdem 14-16 Uhr")
    assert schedule.parsed and not schedule.partial  # same group, so 14-16 belongs to Monday
    schedule = hours.parse("11 - 16 Uhr Mo Mi Do Fr 12 - 16 Uhr")
    assert schedule.partial


# 2026-10-26 is a Monday.
@pytest.mark.parametrize("at, status, extra", [
    (datetime(2026, 10, 26, 10, 0, tzinfo=BERLIN), "open", ("until", "12:00")),
    (datetime(2026, 10, 26, 13, 0, tzinfo=BERLIN), "closed", ("next_opening", "today 14:00")),
    (datetime(2026, 10, 30, 13, 0, tzinfo=BERLIN), "closed", ("next_opening", "Monday 09:00")),  # Friday afternoon
    (datetime(2026, 10, 31, 10, 0, tzinfo=BERLIN), "closed", ("next_opening", "Monday 09:00")),  # Saturday
])
def test_status_at(at, status, extra):
    schedule = hours.parse("Mo - Fr 9-12 Uhr Mo - Do 14-16 Uhr")
    result = hours.status_at(schedule, at)
    assert result["status"] == status
    assert result["kinds"]["opening"][extra[0]] == extra[1]


def test_status_uses_berlin_time():
    schedule = hours.parse("Mo 9-12 Uhr")
    # 08:30 UTC is 09:30 in Berlin (CET, UTC+1, on 2026-10-26).
    from datetime import timezone
    result = hours.status_at(schedule, datetime(2026, 10, 26, 8, 30, tzinfo=timezone.utc))
    assert result["status"] == "open"


def test_holiday_hours_never_decide_status():
    schedule = hours.parse("in den Schulferien Mo-Fr 7:30 bis 17:00 Uhr")
    assert hours.status_at(schedule, datetime(2026, 10, 26, 10, 0, tzinfo=BERLIN))["status"] == "unknown"


def test_holiday_exception_ends_at_sentence_or_closed():
    assert table("An Feiertagen geschlossen. Mo-Fr 9-12") == {"opening": WEEK_9_12}
    assert table("Mo-Fr 9-12 Uhr, in den Ferien 10-12 Uhr. Di 14-16 Uhr") == {
        "opening": {**WEEK_9_12, "Di": "09:00-12:00,14:00-16:00"},
        "holidays": {d: "10:00-12:00" for d in ("Mo", "Di", "Mi", "Do", "Fr")},
    }
