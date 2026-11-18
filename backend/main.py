"""Expose the BARS parser over HTTP."""

from http import HTTPStatus
import logging
from typing import Annotated

from bs4 import ParserRejectedMarkup
from fastapi import FastAPI, File, HTTPException, UploadFile

from parser.bars_parser import Subject, parse_html


MAX_UPLOAD_BYTES = 2 * 1024 * 1024
HTML_CONTENT_TYPES = {"text/html", "application/octet-stream"}

app = FastAPI(title="UniPilot")
logger = logging.getLogger(__name__)


@app.post("/api/parse")
def parse_upload(
    file: Annotated[UploadFile, File(description="An HTML page saved from BARS")],
) -> list[Subject]:
    """Parse one uploaded BARS page and return its subjects in page order."""
    filename = file.filename or ""
    content_type = (file.content_type or "").partition(";")[0].strip().lower()
    if (
        not filename.lower().endswith((".html", ".htm"))
        or content_type not in HTML_CONTENT_TYPES
    ):
        raise HTTPException(
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            "Upload an HTML file with an .html or .htm extension.",
        )

    # FastAPI runs this sync endpoint in a thread pool. Bound the read before
    # handing the contents to Beautiful Soup.
    html = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(html) > MAX_UPLOAD_BYTES:
        raise HTTPException(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "HTML file exceeds 2 MiB.")
    if not html.strip():
        raise HTTPException(HTTPStatus.BAD_REQUEST, "The uploaded file is empty.")

    try:
        subjects = parse_html(html)
    except (ParserRejectedMarkup, UnicodeError, RecursionError) as error:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Could not parse the uploaded HTML.",
        ) from error
    except Exception as error:
        # Exception messages may include parts of the uploaded page.
        logger.error("BARS parser failed with %s", type(error).__name__)
        raise HTTPException(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "Could not process the uploaded file.",
        ) from error

    if not subjects:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "No BARS subjects were found in the uploaded HTML.",
        )
    return subjects
