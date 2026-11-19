from collections.abc import Iterator
import logging

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
    at_limit = BARS_HTML.ljust(5_000_000, b" ")
    response = client.post("/api/parse", files={"file": ("sample.html", at_limit, "text/html")})
    assert response.status_code == 200

    too_large = at_limit + b" "
    response = client.post("/api/parse", files={"file": ("sample.html", too_large, "text/html")})
    assert response.status_code == 413
    assert response.json() == {"detail": "HTML file exceeds 5 MB."}


def test_limits_request_body_without_a_content_length(client: TestClient) -> None:
    def multipart_body() -> Iterator[bytes]:
        # An unsupported filename would produce 415 if the request reached the route.
        yield (
            b"--test-boundary\r\n"
            b'Content-Disposition: form-data; name="file"; filename="sample.txt"\r\n'
            b"Content-Type: text/plain\r\n\r\n"
        )
        for _ in range(6):
            yield b" " * 1_000_000
        yield b"\r\n--test-boundary--\r\n"

    response = client.post(
        "/api/parse",
        content=multipart_body(),
        headers={"Content-Type": "multipart/form-data; boundary=test-boundary"},
    )

    assert "content-length" not in response.request.headers
    assert response.status_code == 413


def test_rejects_multiple_files(client: TestClient) -> None:
    response = client.post("/api/parse", files=[
        ("file", ("one.html", BARS_HTML, "text/html")),
        ("file", ("two.html", BARS_HTML, "text/html")),
    ])

    assert response.status_code == 400


def test_malformed_multipart_does_not_log_request_bytes(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger="python_multipart.multipart"):
        response = client.post(
            "/api/parse",
            content=b"--test-boundary\r\nMalformed Header: fake-student\r\n",
            headers={"Content-Type": "multipart/form-data; boundary=test-boundary"},
        )

    assert response.status_code == 400
    assert "fake-student" not in response.text
    assert all(record.name != "python_multipart.multipart" for record in caplog.records)


@pytest.mark.parametrize(("error", "expected_status", "detail"), [
    (ParserRejectedMarkup("private markup"), 422, "Could not parse the uploaded HTML."),
    (RuntimeError("private markup"), 500, "Could not process the uploaded file."),
])
def test_parse_upload_handles_parser_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    expected_status: int,
    detail: str,
) -> None:
    def reject_markup(html: bytes) -> list[Subject]:
        assert html == BARS_HTML
        raise error

    monkeypatch.setattr(main, "parse_html", reject_markup)

    response = client.post(
        "/api/parse",
        files={"file": ("fake-student.html", BARS_HTML, "text/html")},
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": detail}
    assert "private markup" not in caplog.text
    assert "fake-student.html" not in caplog.text
    if expected_status == 500:
        assert "Unexpected BARS parser failure." in caplog.messages
