"""Parse free-text German opening hours and answer "is it open now?".

The pool stores opening hours as free text in many formats, e.g.
  "Montag bis Freitag 8.00 Uhr bis 16.00 Uhr"
  "Mo - Do 9 - 12.30 Uhr und 13 - 16.30 Uhr Fr 9 - 13 Uhr"
  "Mo, Mi & Fr 08:00 Uhr - 13:00 Uhr Di & Do 13:00 Uhr - 18:00 Uhr"
  "Mo 08:00-17:00;Tu 08:00-17:00;We 08:00-17:00"          (schema.org style)
  "Telefonische Erreichbarkeit: Mo - Fr 9 - 16 Uhr ... sonst nach Vereinbarung"

Approach: find day expressions ("Mo - Fr", "Dienstag und Donnerstag"), attach the
time ranges that follow to those days, and track what kind of hours a section
describes (opening, consultation, phone). Anything that cannot be parsed with
confidence is reported as unknown; we never guess.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Full German names (also "montags"), case-insensitive.
_FULL = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]
_ABBREV = {"mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6,
           "tu": 1, "we": 2, "th": 3, "su": 6}  # English codes are used by schema.org-style values
_GROUP_WORDS = {"werktags": range(0, 5), "werktäglich": range(0, 5), "wochentags": range(0, 5),
                "täglich": range(0, 7), "wochenende": range(5, 7), "am wochenende": range(5, 7)}

# Abbreviations in any case ("Mo", "mo", "MO"), except lowercase "so", an ordinary German word;
# lowercase "so" counts only right after a range dash ("sa-so", "mo - so").
_DAY = (r"(?:(?i:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)s?"
        r"|(?:(?i:mo|di|mi|do|fr|sa|tu|we|th|su)|So|SO|(?<=-)so|(?<=- )so|(?<=–)so)(?![a-zäöüA-ZÄÖÜ]))\.?")
# " ? " is an en dash lost to an encoding error in some sources ("Mo ? Do").
_DAY_SEP = r"(?:\s*(?:-|–|bis|und|u\.|&|\+|,|/|sowie)\s*|\s+\?\s+|\s+)"
DAY_EXPR = re.compile(rf"(?<![A-Za-zäöüÄÖÜ]){_DAY}(?:{_DAY_SEP}{_DAY})*")
GROUP_WORD = re.compile(r"(?i)\b(werktäglich|werktags|wochentags|täglich|am wochenende|wochenende)\b")
# Hour must not continue a number (phone numbers, dates, "8: 00"), but may follow ':' as in "Di.:09:00".
_TIME = r"(?<!\d)(?<!\d[.:])(?<!\d[.:]\s)(\d{1,2})(?:[:.]\s?(\d{2}))?\s*(?:uhr|h)?"
TIME_RANGE = re.compile(rf"(?i){_TIME}\s*(?:-|–|bis|\s\?\s)\s*(?:um\s*)?{_TIME}(?![\d])")
APPOINTMENT = re.compile(r"(?i)vereinbarung|absprache|nach termin")
ALWAYS = re.compile(r"(?i)24\s*(?:h\b|std|stunden)|rund um die uhr|24/7")
# One pass, phone first, so "Telefonische Sprechzeiten" is phone hours, not walk-in consultation.
KIND = re.compile(
    r"(?i)(?P<phone>(?:telefon\w*|tel\.)(?:\s+(?:sprech\w*|erreichbar\w*|beratung\w*|zeiten))?)"
    r"|(?P<consultation>sprechstunde\w*|sprechzeit\w*|beratungszeit\w*|offene beratung)"
    r"|(?P<opening>öffnungszeit\w*|geöffnet)"
    r"|(?P<holidays>\w*ferien\w*|feiertag\w*)"
)
DEFAULT_KIND = "opening"
# Holiday hours are exceptions: kept separately and never used for "open now".
HOLIDAY_KIND = "holidays"
EXCEPT = re.compile(r"(?i)(außer|ausser|nicht)\W*$")
# "am 1. Freitag im Monat", "jeden ersten Montag": monthly, not weekly. Such groups are skipped.
MONTHLY = re.compile(r"(?i)(\d\.|erste\w*|zweite\w*|dritte\w*|vierte\w*|letzte\w*)\s*$")
WORD = re.compile(r"\b[A-Za-zÄÖÜäöüß]{5,12}\b")
# Close to a weekday name but not one ("Montage" = assembly).
NOT_WEEKDAYS = {"montage", "montagen", "feiertag", "feiertage", "feiertags"}
TYPO_SIMILARITY = 0.85


def _fix_weekday_typos(text: str) -> tuple[str, list[str]]:
    """'Mitwoch' -> 'Mittwoch', 'Dientag' -> 'Dienstag'; same length is not required."""

    fixed = []

    def replace(m: re.Match) -> str:
        word = m.group(0)
        lowered = word.lower()
        if lowered in NOT_WEEKDAYS or lowered.rstrip("s") in _FULL:
            return word
        stem = lowered.rstrip("s")
        best = max(_FULL, key=lambda f: SequenceMatcher(None, stem, f).ratio())
        # Length within one letter: keeps "Dienst" (service) from becoming "Dienstag".
        if abs(len(stem) - len(best)) <= 1 and SequenceMatcher(None, stem, best).ratio() >= TYPO_SIMILARITY:
            fixed.append(f"{word} -> {best.capitalize()}")
            return best.capitalize() + ("s" if lowered.endswith("s") and not stem.endswith("s") else "")
        return word

    return WORD.sub(replace, text), fixed

Interval = tuple[time, time]


@dataclass
class Schedule:
    # kind -> weekday (0=Mon) -> list of intervals
    intervals: dict[str, dict[int, list[Interval]]] = field(default_factory=dict)
    appointment: bool = False
    always_open: bool = False
    # Time ranges found without weekdays, e.g. "09:00 - 16:00 Uhr"; never assigned to days.
    times_without_days: list[str] = field(default_factory=list)
    # Day names followed by more day names with only punctuation between, e.g. "Mo ~ Do 9-12".
    dangling_days: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        """Some times could not be tied to weekdays, so parsed days may be incomplete."""

        return self.parsed and (bool(self.times_without_days) or self.dangling_days)

    @property
    def parsed(self) -> bool:
        return self.always_open or any(days for days in self.intervals.values())


def _day_index(token: str) -> int | None:
    lowered = token.rstrip(".").lower()
    if lowered in _ABBREV:
        return _ABBREV[lowered]
    lowered = lowered.rstrip("s")
    return _FULL.index(lowered) if lowered in _FULL else None


def parse_days(expr: str) -> list[int]:
    """'Mo - Fr' -> [0..4]; 'Mo, Mi & Fr' -> [0, 2, 4]; 'Mo-Mi-Do' -> [0, 2, 3] (chains are lists)."""

    parts = re.split(rf"({_DAY_SEP})", expr.strip())
    days = [_day_index(p.strip()) for p in parts[0::2]]
    seps = [{"?": "-"}.get(s.strip().lower(), s.strip().lower()) or " " for s in parts[1::2]]
    if any(d is None for d in days):
        return []
    if len(days) == 2 and seps[0] in ("-", "–", "bis"):
        start, end = days
        return list(range(start, end + 1)) if start <= end else list(range(start, 7)) + list(range(0, end + 1))
    if len(days) > 2 and all(s in ("-", "–") for s in seps):
        return sorted(set(days))  # "Mo-Mi-Do" lists days rather than nesting ranges
    result: list[int] = []
    for i, day in enumerate(days):
        if i > 0 and seps[i - 1] in ("-", "–", "bis") and result:
            result += list(range(result[-1] + 1, day + 1))
        else:
            result.append(day)
    return sorted(set(result))


def _to_time(hour: str, minute: str | None) -> time | None:
    h, m = int(hour), int(minute or 0)
    if h == 24 and m == 0:
        return time(23, 59)
    if 0 <= h <= 23 and 0 <= m <= 59:
        return time(h, m)
    return None


def parse(text: str | None) -> Schedule:
    schedule = Schedule()
    if not text or not text.strip():
        schedule.notes.append("no opening hours in the data")
        return schedule
    if ALWAYS.search(text):
        schedule.always_open = True
        schedule.notes.append("text says open 24 hours")
    schedule.appointment = bool(APPOINTMENT.search(text))
    text, typos = _fix_weekday_typos(text)
    if typos:
        schedule.notes.append(f"read misspelled weekdays: {', '.join(typos)}")

    events = []  # (position, type, payload)
    for m in DAY_EXPR.finditer(text):
        events.append((m.start(), m.end(), "days", parse_days(m.group(0))))
    for m in GROUP_WORD.finditer(text):
        events.append((m.start(), m.end(), "days", list(_GROUP_WORDS[m.group(1).lower()])))
    for m in TIME_RANGE.finditer(text):
        start, end = _to_time(m.group(1), m.group(2)), _to_time(m.group(3), m.group(4))
        if start and end and start < end:
            events.append((m.start(), m.end(), "time", (start, end)))
    for m in KIND.finditer(text):
        events.append((m.start(), m.end(), "kind", m.lastgroup))
    events.sort()

    kind, regular_kind, days = DEFAULT_KIND, DEFAULT_KIND, []
    kind_end, holiday_used = 0, False
    days_end, days_used = 0, True
    # Size of the day group that set each interval: a narrower group overrides ("Mo-Fr 8-19 ... Fr 8-17").
    group_size: dict[tuple, int] = {}
    for start, end, etype, payload in events:
        if etype == "kind":
            kind, kind_end = payload, end
            if kind != HOLIDAY_KIND:
                regular_kind = kind
            holiday_used = False
        elif etype == "days":
            if MONTHLY.search(text[max(0, start - 12):start]):
                schedule.notes.append(f"monthly hours ignored: {text[max(0, start - 12):end].strip()!r}")
                payload = []
            elif EXCEPT.search(text[max(0, start - 12):start]):
                # "Mo-Fr 9-12 und nachmittags, außer freitags 14-16": remove days from the current group.
                payload = [d for d in days if d not in payload]
            gap = text[days_end:start]
            if not days_used and days and not re.search(r"[A-Za-zäöüÄÖÜ\d]", gap):
                # Two day groups separated only by punctuation: likely an unrecognised separator.
                schedule.dangling_days = True
            if kind == HOLIDAY_KIND and (
                holiday_used or re.search(r"(?i)geschlossen|\.\s|;|\n", text[kind_end:start])
            ):
                # The holiday exception is over: it already had its times ("in den Ferien 8-12 Uhr. Mo-Fr ..."),
                # or it ended in a sentence ("An Feiertagen geschlossen. Mo-Fr ...").
                kind = regular_kind
            days, days_end, days_used = payload, end, False
        elif etype == "time":
            if not days:
                schedule.times_without_days.append(f"{_fmt(payload[0])}-{_fmt(payload[1])}")
                continue
            days_used = True
            holiday_used = holiday_used or kind == HOLIDAY_KIND
            per_day = schedule.intervals.setdefault(kind, {})
            for day in days:
                existing = per_day.setdefault(day, [])
                if payload in existing:
                    continue
                for iv in list(existing):
                    overlaps = payload[0] < iv[1] and iv[0] < payload[1]
                    if overlaps and len(days) < group_size.get((kind, day, iv), 7):
                        existing.remove(iv)
                existing.append(payload)
                group_size[(kind, day, payload)] = len(days)

    if schedule.times_without_days:
        schedule.notes.append(
            f"times without weekdays (not used): {', '.join(schedule.times_without_days)}"
        )
    if schedule.dangling_days:
        schedule.notes.append("some weekdays could not be tied to times (unrecognised separator)")
    if schedule.appointment:
        schedule.notes.append("mentions appointments (nach Vereinbarung)")
    if not schedule.parsed and not schedule.appointment:
        schedule.notes.append("could not read days and times from the text")
    for per_day in schedule.intervals.values():
        for intervals in per_day.values():
            intervals.sort()
    return schedule


def _fmt(t: time) -> str:
    return t.strftime("%H:%M")


def status_at(schedule: Schedule, at: datetime) -> dict:
    """Open/closed per kind of hours at a given time, plus the next opening."""

    at = at.astimezone(BERLIN)
    if schedule.always_open:
        return {"status": "open", "detail": "open 24 hours", "kinds": {}}
    if not schedule.parsed:
        status = "by_appointment" if schedule.appointment else "unknown"
        return {"status": status, "kinds": {}}

    kinds = {}
    for kind, per_day in schedule.intervals.items():
        today = per_day.get(at.weekday(), [])
        now = at.time()
        current = next((iv for iv in today if iv[0] <= now < iv[1]), None)
        if current:
            kinds[kind] = {"open": True, "until": _fmt(current[1])}
            continue
        nxt = None
        for offset in range(0, 8):
            day = (at + timedelta(days=offset))
            for iv in per_day.get(day.weekday(), []):
                if offset == 0 and iv[0] <= now:
                    continue
                nxt = f"{DAY_NAMES[day.weekday()]} {_fmt(iv[0])}" if offset else f"today {_fmt(iv[0])}"
                break
            if nxt:
                break
        kinds[kind] = {"open": False, "next_opening": nxt}

    regular = [k for k in kinds if k != HOLIDAY_KIND]
    if not regular:
        return {"status": "unknown", "kinds": kinds, "detail": "only holiday hours are given"}
    primary = next((k for k in ("opening", "consultation") if k in kinds), regular[0])
    status = "open" if kinds[primary]["open"] else "closed"
    result = {"status": status, "based_on": primary, "kinds": kinds}
    if schedule.partial:
        result["confidence"] = "partial: some times in the text could not be tied to weekdays"
    return result


def weekly_table(schedule: Schedule) -> dict[str, dict[str, list[str]]]:
    return {
        kind: {DAY_NAMES[d]: [f"{_fmt(a)}-{_fmt(b)}" for a, b in ivs] for d, ivs in sorted(per_day.items())}
        for kind, per_day in schedule.intervals.items()
    }
