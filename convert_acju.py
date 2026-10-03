#!/usr/bin/env python3
"""
convert_acju.py - convert ACJU prayer-time PDF timetables into one JSON file.

README
------
Dependency (only one): pdfplumber      ->  pip install -r requirements.txt

Input : a folder of PDFs named  NN-REGION-MM-Mon.pdf
        e.g. 01-COLOMBO-DISTRICT-GAMPAHA-DISTRICT-KALUTARA-DISTRICT-10-Oct.pdf
Output: one JSON file (default prayer_times.json), optionally one CSV per zone.

Windows (PowerShell / cmd):
    py -3 -m venv .venv
    .venv\\Scripts\\activate
    pip install -r requirements.txt
    python convert_acju.py C:\\path\\to\\pdfs prayer_times.json --csv

macOS / Linux:
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python3 convert_acju.py ~/path/to/pdfs prayer_times.json --csv

Self-test (no PDFs needed):
    python convert_acju.py --self-test

Exit code is 0 when no problems are found, 1 when the validation report lists
problems (the JSON is still written so you can inspect it), 2 on fatal errors.
"""

# requirements: pdfplumber

import argparse
import calendar
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

SOURCE = "ACJU (All Ceylon Jamiyyathul Ulama)"
SAHR_END_MINUTES_BEFORE_FAJR = 2
APARTMENT_ADJUSTMENTS = [
    {"floors": "06-35", "meters": "24-140", "fajr": -1, "sunrise": -1, "maghrib": 1, "isha": 1},
    {"floors": "35-87", "meters": "140-350", "fajr": -2, "sunrise": -2, "maghrib": 2, "isha": 2},
]

ZONES = {
    "01": "Colombo, Gampaha, Kalutara",
    "02": "Jaffna, Nallur",
    "03": "Mullaitivu (except Nallur), Kilinochchi, Vavuniya",
    "04": "Mannar, Puttalam",
    "05": "Anuradhapura, Polonnaruwa",
    "06": "Kurunegala",
    "07": "Kandy, Matale, Nuwara Eliya",
    "08": "Batticaloa, Ampara",
    "09": "Trincomalee",
    "10": "Badulla, Monaragala, Padiyatalawa, Dehiaththakandiya",
    "11": "Ratnapura, Kegalle",
    "12": "Galle, Matara",
    "13": "Hambantota",
}

PRAYERS = ["fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha"]  # LUHR->dhuhr, MAGRIB->maghrib
MAX_JUMP_MINUTES = 5
MONTH_ABBR = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}

FILENAME_RE = re.compile(r"^(\d{2})-(.+)-(\d{2})-([A-Za-z]{3})\.pdf$", re.IGNORECASE)
TIME = r"\d{1,2}:\d{2}\s*[AaPp][Mm]"
ROW_RE = re.compile(
    rf"^\s*(\d{{1,2}})-([A-Za-z]{{3}})\s+((?:{TIME}\s+){{5}}{TIME})\s*$"
)
TIME_RE = re.compile(TIME)
ZONE_RE = re.compile(r"Zone\s*:?\s*(\d{1,2})", re.IGNORECASE)


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------
def to_24h(text):
    """Convert '4:42 AM' / '12:02 PM' to 'HH:MM' (24-hour). Raises ValueError."""
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*([AaPp])[Mm]\s*", text)
    if not m:
        raise ValueError(f"not a 12-hour time: {text!r}")
    hour, minute, ap = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    if not (1 <= hour <= 12 and 0 <= minute <= 59):
        raise ValueError(f"time out of range: {text!r}")
    hour = hour % 12 + (12 if ap == "P" else 0)
    return f"{hour:02d}:{minute:02d}"


def parse_row(line):
    """Parse one text line. Returns (day, month_abbr, {prayer: 'HH:MM'}) or None."""
    m = ROW_RE.match(line)
    if not m:
        return None
    times = TIME_RE.findall(m.group(3))
    try:
        values = [to_24h(t) for t in times]
    except ValueError:
        return None
    return int(m.group(1)), m.group(2).lower(), dict(zip(PRAYERS, values))


def parse_filename(name):
    """Return (zone, month_number, region_text) from 'NN-REGION-MM-Mon.pdf'.

    Raises ValueError with a helpful message if the name doesn't match.
    """
    m = FILENAME_RE.match(name)
    if not m:
        raise ValueError("name does not match NN-REGION-MM-Mon.pdf")
    zone, region, month, abbr = m.group(1), m.group(2), int(m.group(3)), m.group(4).lower()
    if not 1 <= month <= 12:
        raise ValueError(f"month number {month:02d} is not 01-12")
    if MONTH_ABBR.get(abbr) != month:
        raise ValueError(f"month number {month:02d} does not agree with '{m.group(4)}'")
    return zone, month, region


def parse_pdf(path, month):
    """Extract rows and the PDF's zone label from one PDF.

    Returns (rows, pdf_zone, issues) where rows is a list of
    (day, times_dict) and issues is a list of problem strings.
    """
    import pdfplumber  # imported lazily so --self-test works without it

    rows, issues, pdf_zone = [], [], None
    with pdfplumber.open(path) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    zm = ZONE_RE.search(text)
    if zm:
        pdf_zone = f"{int(zm.group(1)):02d}"
    for line in text.splitlines():
        parsed = parse_row(line)
        if not parsed:
            continue
        day, abbr, times = parsed
        if MONTH_ABBR.get(abbr) != month:
            issues.append(f"row '{line.strip()}' has month '{abbr}', expected month {month:02d}")
            continue
        rows.append((day, times))
    return rows, pdf_zone, issues


# --------------------------------------------------------------------------
# Collection, validation, output
# --------------------------------------------------------------------------
def minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def expected_days(month):
    """Allowed day counts for a month (year-agnostic: Feb may be 28 or 29)."""
    last = calendar.monthrange(2024, month)[1]
    return {last, last - 1} if month == 2 else {last}


def collect(folder):
    """Parse every PDF in folder. Returns (data, file_reports, problems).

    data: {zone: {"MM-DD": times}}; file_reports: [(filename, n_days, ok)].
    """
    problems, reports, data = [], [], {}
    pdfs = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    if not pdfs:
        raise SystemExit(f"error: no PDF files found in {folder}")
    for path in pdfs:
        file_problems = []

        def flag(msg, fp=file_problems, n=path.name):
            fp.append(f"{n}: {msg}")

        try:
            zone, month, _ = parse_filename(path.name)
        except ValueError as e:
            flag(str(e))
            problems += file_problems
            reports.append((path.name, 0, False))
            continue
        if zone not in ZONES:
            flag(f"zone {zone} is not a known zone (01-13)")
        try:
            rows, pdf_zone, issues = parse_pdf(path, month)
        except Exception as e:  # corrupt/encrypted PDF etc.
            flag(f"could not read PDF: {e}")
            problems += file_problems
            reports.append((path.name, 0, False))
            continue
        for msg in issues:
            flag(msg)
        if pdf_zone is None:
            flag("no 'Zone: NN' label found in PDF")
        elif pdf_zone != zone:
            flag(f"zone mismatch: file name says {zone}, PDF says {pdf_zone}")
        if not rows:
            flag("no data rows found")

        days = data.setdefault(zone, {})
        seen = set()
        for day, times in rows:
            try:
                key = f"{month:02d}-{day:02d}"
                dt.date(2024, month, day)  # validates the day number
            except ValueError:
                flag(f"invalid date {day}/{month:02d}")
                continue
            if key in seen or key in days:
                flag(f"duplicate date {key} for zone {zone}")
                continue
            seen.add(key)
            days[key] = times
        if rows:
            allowed = expected_days(month)
            if len(seen) not in allowed:
                last = calendar.monthrange(2024, month)[1]
                missing = [f"{month:02d}-{d:02d}" for d in range(1, last + 1)
                           if f"{month:02d}-{d:02d}" not in seen]
                flag(f"expected {'/'.join(map(str, sorted(allowed)))} days, found {len(seen)}; "
                     f"missing: {', '.join(missing) if missing else 'none'}")
        problems += file_problems
        reports.append((path.name, len(seen), not file_problems))
    return data, reports, problems


def validate(data):
    """Check time order and day-to-day jumps for all zones. Returns problem list."""
    problems = []
    for zone in sorted(data):
        days = dict(sorted(data[zone].items()))
        prev_key = None
        for key, t in days.items():
            mins = [minutes(t[p]) for p in PRAYERS]
            if any(a >= b for a, b in zip(mins, mins[1:])):
                problems.append(f"zone {zone} {key}: times out of order "
                                f"({', '.join(f'{p} {t[p]}' for p in PRAYERS)})")
            if prev_key:
                d1 = dt.date(2024, *map(int, prev_key.split("-")))
                d2 = dt.date(2024, *map(int, key.split("-")))
                if (d2 - d1).days == 1:
                    for p in PRAYERS:
                        diff = abs(minutes(t[p]) - minutes(days[prev_key][p]))
                        if diff > MAX_JUMP_MINUTES:
                            problems.append(
                                f"zone {zone} {prev_key} -> {key}: {p} jumps {diff} min "
                                f"({days[prev_key][p]} -> {t[p]})")
            prev_key = key
    return problems


def build_json(data):
    """Assemble the output structure; all 13 zones are always present."""
    regions = {}
    for zone, name in ZONES.items():
        regions[zone] = {"name": name, "days": dict(sorted(data.get(zone, {}).items()))}
    return {
        "source": SOURCE,
        "generated": dt.datetime.now().replace(microsecond=0).isoformat(),
        "sahr_end_minutes_before_fajr": SAHR_END_MINUTES_BEFORE_FAJR,
        "apartment_adjustments": APARTMENT_ADJUSTMENTS,
        "regions": regions,
    }


def write_csv(doc, out_dir):
    """Write one CSV per zone that has data."""
    for zone, region in doc["regions"].items():
        if not region["days"]:
            continue
        with open(out_dir / f"zone_{zone}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date"] + PRAYERS)
            for key, t in region["days"].items():
                w.writerow([key] + [t[p] for p in PRAYERS])


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------
def self_test():
    """Prove the row regex and time conversion work on a sample row."""
    assert to_24h("4:42 AM") == "04:42"
    assert to_24h("12:02 PM") == "12:02"
    assert to_24h("12:05 AM") == "00:05"
    assert to_24h("7:12 PM") == "19:12"
    row = parse_row("1-Oct 4:42 AM 5:59 AM 12:02 PM 3:16 PM 6:03 PM 7:12 PM")
    assert row == (1, "oct", {"fajr": "04:42", "sunrise": "05:59", "dhuhr": "12:02",
                              "asr": "15:16", "maghrib": "18:03", "isha": "19:12"}), row
    assert parse_row("Zone: 01") is None
    assert parse_row("1-Oct 4:42 AM 5:59 AM 12:02 PM 3:16 PM 6:03 PM") is None  # only 5 times
    assert parse_filename("01-COLOMBO-DISTRICT-GAMPAHA-DISTRICT-KALUTARA-DISTRICT-10-Oct.pdf")[:2] == ("01", 10)
    for bad in ("notes.pdf", "01-COLOMBO-10-Nov.pdf"):
        try:
            parse_filename(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad} should have been rejected")
    print("Self-test passed.")


test_sample_row = self_test  # lets pytest pick it up


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Convert ACJU prayer-time PDFs to one JSON file.")
    ap.add_argument("pdf_folder", nargs="?", help="folder containing the PDF files")
    ap.add_argument("output", nargs="?", default="prayer_times.json", help="output JSON (default: prayer_times.json)")
    ap.add_argument("--csv", action="store_true", help="also write one CSV per zone next to the JSON")
    ap.add_argument("--self-test", action="store_true", help="run the built-in sample test and exit")
    args = ap.parse_args(argv)

    if args.self_test:
        self_test()
        return 0
    if not args.pdf_folder:
        ap.error("pdf_folder is required")
    folder = Path(args.pdf_folder)
    if not folder.is_dir():
        print(f"error: {folder} is not a folder", file=sys.stderr)
        return 2
    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        print("error: pdfplumber is not installed. Run: pip install -r requirements.txt", file=sys.stderr)
        return 2

    data, reports, problems = collect(folder)
    problems += validate(data)
    doc = build_json(data)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.csv:
        write_csv(doc, out.parent)

    print("=== Validation report ===")
    for name, n, ok in reports:
        print(f"{'OK  ' if ok else 'FAIL'} {name}: {n} days")
    empty = [z for z in ZONES if not data.get(z)]
    if empty:
        print(f"Note: no data for zone(s): {', '.join(empty)}")
    print()
    if problems:
        print(f"{len(problems)} problem(s) found:")
        for i, p in enumerate(problems, 1):
            print(f"  {i}. {p}")
    else:
        print("No problems found")
    print(f"\nWrote {out}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
