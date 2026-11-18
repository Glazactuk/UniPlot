from collections.abc import Iterator

from bs4 import ParserRejectedMarkup
from fastapi.testclient import TestClient
import pytest

from backend import main
from parser.bars_parser import Subject


BARS_HTML = """
    <div data-bs-toggle="collapse" data-bs-target="#s_ss_0">Математика, преподаватель</div>
    <div id="s_ss_0"><table>
        <tr><td>Матрицы</td><td>37,5%</td><td>4 (21.09.26-27.09.26)</td><td>4,5 (23.09.26)</td></tr>
        <tr><td>Определители</td><td>62,5%</td><td>09.10.26</td><td></td></tr>
    </table></div>
    <div data-bs-toggle="collapse" data-bs-target="#s_ss_1">Физика</div>
    <div id="s_ss_1"><table>
        <tr><td>Контрольная</td><td>100</td><td>17.11.26</td><td>5 (18.11.26)</td></tr>
    </table></div>
""".encode("utf-8")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(main.app) as client:
        yield client


@pytest.mark.parametrize(("filename", "content_type"), [
    ("sample.html", "text/html; charset=utf-8"),
    ("sample.HTM", "application/octet-stream"),
])
def test_parse_upload_returns_subjects(
    client: TestClient,
    filename: str,
    content_type: str,
) -> None:
    response = client.post("/api/parse", files={"file": (filename, BARS_HTML, content_type)})

    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "Математика",
            "assessments": [
                {
                    "name": "Матрицы",
                    "weight": 37.5,
                    "scheduled_start": "2026-09-21",
                    "scheduled_end": "2026-09-27",
                    "grade": 4.5,
                    "grading_date": "2026-09-23",
                },
                {
                    "name": "Определители",
                    "weight": 62.5,
                    "scheduled_start": "2026-10-09",
                    "scheduled_end": None,
                    "grade": None,
                    "grading_date": None,
                },
            ],
        },
        {
            "name": "Физика",
            "assessments": [
                {
                    "name": "Контрольная",
                    "weight": 100,
                    "scheduled_start": "2026-11-17",
                    "scheduled_end": None,
                    "grade": 5,
                    "grading_date": "2026-11-18",
                },
            ],
        },
    ]


@pytest.mark.parametrize(("filename", "content_type", "body", "expected_status"), [
    ("sample.txt", "text/html", BARS_HTML, 415),
    ("sample.html", "text/plain", BARS_HTML, 415),
    ("sample.html", "text/html", b"", 400),
    ("sample.html", "text/html", b" \n\t", 400),
    ("sample.html", "text/html", b"<html><p>No subjects</p></html>", 422),
    ("sample.html", "text/html", b"Not HTML", 422),
])
def test_parse_upload_rejects_invalid_files(
    client: TestClient,
    filename: str,
    content_type: str,
    body: bytes,
    expected_status: int,
) -> None:
    response = client.post("/api/parse", files={"file": (filename, body, content_type)})

    assert response.status_code == expected_status
    assert isinstance(response.json()["detail"], str)


def test_parse_upload_requires_a_file(client: TestClient) -> None:
    response = client.post("/api/parse")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "file"]


def test_upload_size_limit(client: TestClient) -> None:
    at_limit = BARS_HTML.ljust(main.MAX_UPLOAD_BYTES, b" ")
    response = client.post("/api/parse", files={"file": ("sample.html", at_limit, "text/html")})
    assert response.status_code == 200

    too_large = at_limit + b" "
    response = client.post("/api/parse", files={"file": ("sample.html", too_large, "text/html")})
    assert response.status_code == 413


@pytest.mark.parametrize(("error", "expected_status", "detail"), [
    (ParserRejectedMarkup("private markup"), 422, "Could not parse the uploaded HTML."),
    (RuntimeError("private markup"), 500, "Could not process the uploaded file."),
])
def test_parse_upload_handles_parser_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
    detail: str,
) -> None:
    def reject_markup(html: bytes) -> list[Subject]:
        assert html == BARS_HTML
        raise error

    monkeypatch.setattr(main, "parse_html", reject_markup)

    response = client.post("/api/parse", files={"file": ("sample.html", BARS_HTML, "text/html")})

    assert response.status_code == expected_status
    assert response.json() == {"detail": detail}
