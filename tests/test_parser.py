from datetime import date
import json
from pathlib import Path
import subprocess
import sys

import pytest

from parser.bars_parser import Assessment, Subject, parse_html


@pytest.fixture
def bars_html() -> str:
    return """
        <div data-bs-target="#s_ss_1" data-bs-toggle="collapse">
            Математика, преподаватель <span class="badge">сдать до 24.12.2026</span>
        </div>
        <div id="s_ss_0">
            <table><tr><td>Контрольная работа</td><td>100</td>
            <td>12 (17.11.26)</td><td>5 (18.11.26)</td></tr></table>
        </div>
        <div data-bs-target="#s_ss_0" data-bs-toggle="collapse">Физика</div>
        <div id="s_ss_1">
            <table>
                <thead><tr><th>Мероприятие</th><th>Вес</th><th>Срок</th><th>Оценка</th></tr></thead>
                <tbody>
                    <tr><td colspan="4">Текущий контроль:</td></tr>
                    <tr>
                        <td>1. <strong>Матрицы</strong>
                            <span data-bs-toggle="collapse">(критерии)</span></td>
                        <td>37,5%</td><td>4 (21.09.26 – 27.09.2026)</td><td>4,5 (23.09.26)</td>
                    </tr>
                    <tr><td colspan="4">Критерии</td></tr>
                    <tr><td>2. Определители</td><td>62,5</td><td>09.10.26</td><td> &nbsp; </td></tr>
                    <tr><td colspan="2">Контрольная неделя №1</td><td>4</td><td>4,5</td></tr>
                    <tr><td colspan="3">Итоговая оценка:</td><td>4,5</td></tr>
                </tbody>
            </table>
        </div>
    """


def test_matches_subjects_to_panels_and_extracts_assessments(bars_html: str) -> None:
    assert parse_html(bars_html.encode("utf-8")) == [
        Subject("Математика", [
            Assessment("1. Матрицы", 37.5, date(2026, 9, 21), date(2026, 9, 27), 4.5, date(2026, 9, 23)),
            Assessment("2. Определители", 62.5, date(2026, 10, 9), None, None, None),
        ]),
        Subject("Физика", [
            Assessment("Контрольная работа", 100, date(2026, 11, 17), None, 5, date(2026, 11, 18)),
        ]),
    ]


def test_keeps_subjects_and_named_rows_when_fields_are_missing() -> None:
    html = """
        <div data-bs-target="#s_ss_empty" data-bs-toggle="collapse">История</div>
        <div data-bs-target="#s_ss_0" data-bs-toggle="collapse">Химия</div>
        <div id="s_ss_0"><table>
            <tr><td></td><td>25</td><td>5 (26.02.26)</td><td>5</td></tr>
            <tr><td>Лабораторная</td><td>?</td><td>5 (30.02.26)</td><td>5 (99.09.26)</td></tr>
            <tr><td>Тест</td><td>50</td></tr>
        </table></div>
    """

    assert parse_html(html) == [
        Subject("История", []),
        Subject("Химия", [
            Assessment("Лабораторная", None, None, None, 5, None),
            Assessment("Тест", 50, None, None, None, None),
        ]),
    ]


@pytest.mark.parametrize("schedule", [
    "4 (27.09.26-21.09.26)",
    "4 (21.09.26-31.09.26)",
    "4 (21.09.26-)",
    "4",
])
def test_invalid_schedules_do_not_discard_grades(schedule: str) -> None:
    html = f"""
        <div data-bs-target="#s_ss_0" data-bs-toggle="collapse">Практика</div>
        <div id="s_ss_0"><table>
            <tr><td>Отчёт</td><td>100</td><td>{schedule}</td><td>Зачтено (28.09.26)</td></tr>
        </table></div>
    """
    assessment, = parse_html(html)[0].assessments
    assert assessment == Assessment("Отчёт", 100, None, None, "Зачтено", date(2026, 9, 28))


def test_empty_document() -> None:
    assert parse_html("<html><body></body></html>") == []


def test_cli_exports_utf8_json_with_iso_dates_and_nulls(tmp_path: Path, bars_html: str) -> None:
    script = Path(__file__).resolve().parents[1] / "parser" / "bars_parser.py"
    data = tmp_path / "data"
    data.mkdir()
    (data / "sample.html").write_text(bars_html, encoding="utf-8")

    subprocess.run([sys.executable, str(script)], cwd=tmp_path, check=True)

    payload = (data / "grades.json").read_text(encoding="utf-8")
    assert "Математика" in payload
    mathematics, physics = json.loads(payload)
    assert mathematics["assessments"] == [
        {
            "name": "1. Матрицы",
            "weight": 37.5,
            "scheduled_start": "2026-09-21",
            "scheduled_end": "2026-09-27",
            "grade": 4.5,
            "grading_date": "2026-09-23",
        },
        {
            "name": "2. Определители",
            "weight": 62.5,
            "scheduled_start": "2026-10-09",
            "scheduled_end": None,
            "grade": None,
            "grading_date": None,
        },
    ]
    assert physics["name"] == "Физика"
