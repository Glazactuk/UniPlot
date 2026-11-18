"""Parse assessments from a locally saved BARS page."""

import argparse
from dataclasses import asdict, dataclass
from datetime import date
import json
from math import isfinite
from pathlib import Path
import re

from bs4 import BeautifulSoup, Tag


@dataclass
class Assessment:
    name: str
    weight: int | float | None
    scheduled_start: date | None
    scheduled_end: date | None
    grade: int | float | str | None
    grading_date: date | None


@dataclass
class Subject:
    name: str
    assessments: list[Assessment]


DATE = r"[0-9]{1,2}\.[0-9]{1,2}\.(?:[0-9]{4}|[0-9]{2})"
DATE_RANGE = re.compile(rf"({DATE})(?:\s*[-–—]\s*({DATE}))?")
NUMBER = re.compile(r"[0-9]+(?:[.,][0-9]+)?")
PASS_FAIL_GRADES = {"зачтено", "зачёт", "зачет", "не зачтено", "незачёт", "незачет"}


def _text(tag: Tag) -> str:
    return " ".join(tag.get_text(" ", strip=True).split())


def _date(text: str) -> date | None:
    if not re.fullmatch(DATE, text):
        return None
    day, month, year = text.split(".")
    try:
        return date(int(year) + (2000 if len(year) == 2 else 0), int(month), int(day))
    except ValueError:
        return None


def _schedule(text: str) -> tuple[date | None, date | None]:
    # BARS prefixes the parenthesized dates with the teaching week.
    if match := re.fullmatch(r"(?:[0-9]+\s*)?\(\s*(.*?)\s*\)", text):
        text = match[1]
    dates = DATE_RANGE.fullmatch(text)
    if dates is None:
        return None, None

    start = _date(dates[1])
    end = _date(dates[2]) if dates[2] is not None else None
    if start is None or (dates[2] is not None and (end is None or end < start)):
        return None, None
    return start, end


def _number(text: str) -> int | float | None:
    if not NUMBER.fullmatch(text):
        return None
    normalized = text.replace(",", ".")
    try:
        if "." not in normalized:
            return int(normalized)
        value = float(normalized)
        return value if isfinite(value) else None
    except (ValueError, OverflowError):
        return None


def _grade(text: str) -> tuple[int | float | str | None, date | None]:
    value, _, date_text = text.partition("(")
    value = value.strip()
    grading_date = _date(date_text[:-1].strip()) if date_text.endswith(")") else None
    if value.casefold() in PASS_FAIL_GRADES:
        return value, grading_date
    return _number(value), grading_date


def _assessment(row: Tag) -> Assessment | None:
    cells = row.find_all(["th", "td"], recursive=False)
    # The BARS headers, criteria and summary rows span multiple columns.
    if not 1 <= len(cells) <= 4 or any(
        cell.name != "td" or cell.get("colspan", "1") != "1" for cell in cells
    ):
        return None

    for criteria_link in reversed(cells[0].select('[data-bs-toggle="collapse"]')):
        criteria_link.decompose()

    values = [_text(cell) for cell in cells]
    # Treat absent trailing cells like empty cells.
    name, weight, schedule, grade = values + [""] * (4 - len(values))
    if not name:
        return None

    scheduled_start, scheduled_end = _schedule(schedule)
    grade_value, grading_date = _grade(grade)
    return Assessment(
        name=name,
        weight=_number(weight.removesuffix("%").strip()),
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        grade=grade_value,
        grading_date=grading_date,
    )


def parse_html(html: str | bytes) -> list[Subject]:
    """Extract subjects and their assessments in page order."""
    soup = BeautifulSoup(html, "html.parser")
    subjects: list[Subject] = []
    seen_panels: set[str] = set()

    for heading in soup.select('[data-bs-toggle="collapse"][data-bs-target^="#s_ss_"]'):
        panel_id = str(heading["data-bs-target"])[1:]
        if panel_id in seen_panels:
            continue
        for badge in reversed(heading.select(".badge")):
            badge.decompose()
        name = _text(heading).partition(",")[0].strip()
        if not name:
            continue

        seen_panels.add(panel_id)
        panel = soup.find(id=panel_id)
        table = panel.find("table") if panel is not None else None

        assessments: list[Assessment] = []
        if table is not None:
            for row in table.select(":scope > tr, :scope > tbody > tr"):
                if (assessment := _assessment(row)) is not None:
                    assessments.append(assessment)
        subjects.append(Subject(name, assessments))

    return subjects


def parse_file(path: Path) -> list[Subject]:
    """Read the saved HTML as bytes so Beautiful Soup can detect its encoding."""
    return parse_html(path.read_bytes())


def _encode_date(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Cannot encode {type(value).__name__} as JSON")


def export_json(subjects: list[Subject], path: Path) -> None:
    """Write a UTF-8 JSON array, converting Python dates to ISO 8601."""
    records = [asdict(subject) for subject in subjects]
    payload = json.dumps(records, ensure_ascii=False, indent=2, default=_encode_date)
    path.write_text(payload + "\n", encoding="utf-8")


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--input", type=Path, default=Path("data/sample.html"))
    cli.add_argument("--output", type=Path, default=Path("data/grades.json"))
    args = cli.parse_args()

    try:
        if args.input.resolve() == args.output.resolve():
            cli.error("input and output must be different files")
        export_json(parse_file(args.input), args.output)
    except OSError as error:
        cli.exit(1, f"{cli.prog}: {error}\n")


if __name__ == "__main__":
    main()
