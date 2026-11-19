"""Expose the BARS parser over HTTP."""

from http import HTTPStatus
import logging
from typing import Annotated

from bs4 import ParserRejectedMarkup
from fastapi import FastAPI, File, HTTPException, UploadFile

from parser.bars_parser import Subject, parse_html


MAX_UPLOAD_BYTES = 5_000_000
MULTIPART_OVERHEAD_BYTES = 64 * 1024
HTML_CONTENT_TYPES = {"text/html", "application/octet-stream"}

logger = logging.getLogger(__name__)
# Multipart diagnostics can include bytes from a malformed request.
logging.getLogger("python_multipart.multipart").disabled = True
# Keep request and exception details out of FastAPI telemetry.
app = FastAPI(title="UniPilot", telemetry={"tracing": False, "logs": False})


@app.post(
    "/api/parse",
    # Allow space for multipart headers and boundaries around a 5 MB file.
    max_body_size=MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES,
    form_limits={"max_files": 1, "max_fields": 0},
)
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
            "Upload an .html or .htm file as text/html or application/octet-stream.",
        )

    # The request limit includes multipart overhead. Check the file itself here.
    # Reading the bytes lets Beautiful Soup detect the original page encoding.
    html = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(html) > MAX_UPLOAD_BYTES:
        raise HTTPException(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "HTML file exceeds 5 MB.")
    if not html.strip():
        raise HTTPException(HTTPStatus.BAD_REQUEST, "The uploaded file is empty.")

    try:
        subjects = parse_html(html)
    except (ParserRejectedMarkup, UnicodeError, RecursionError):
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Could not parse the uploaded HTML.",
        ) from None
    except Exception:
        # Log a fixed message because the parser exception can contain page text.
        logger.error("Unexpected BARS parser failure.")
        raise HTTPException(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "Could not process the uploaded file.",
        ) from None

    if not subjects:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "No BARS subjects were found in the uploaded HTML.",
        )
    return subjects
