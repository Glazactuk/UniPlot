# UniPilot

UniPilot is an application for tracking university grades,
assessments, and academic deadlines.

## Features

- Extract grades from BARS HTML pages
- Track upcoming assessments
- Store assessment dates and weights
- Export structured data to JSON

## Technologies

- Python
- BeautifulSoup
- FastAPI and Uvicorn
- pytest

## Installation

Use Python 3.12 or newer. From the repository root, install the dependencies
with `python -m pip install -r requirements.txt`.

## Local parser

Save a BARS HTML page as `data/sample.html`, then run the parser from the
repository root.

```sh
python parser/bars_parser.py
```

The parser writes UTF-8 JSON to `data/grades.json`. Use `--input` and
`--output` to choose different paths. The `data/` directory is ignored by Git
because the source and output can contain private grades.

Each JSON subject has a name and a list of assessments. Weights are percentages,
so a weight of 25 is exported as `25`. Dates use `YYYY-MM-DD`. A single
scheduled date fills `scheduled_start` and leaves `scheduled_end` as `null`.
A range fills both fields. Two-digit BARS years are interpreted as 2000–2099.
Missing grades and unparseable dates are exported as `null`.

## FastAPI backend

Start the development server from the repository root.

```sh
python -m uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000/docs` to try the endpoint in Swagger UI, or use curl.

```sh
curl --fail-with-body -F 'file=@data/sample.html;type=text/html' http://127.0.0.1:8000/api/parse
```

`POST /api/parse` accepts a multipart form with a `file` field. Upload a BARS
`.html` or `.htm` file of up to 2 MiB with media type `text/html` or
`application/octet-stream`. The response is a JSON array of subjects in page
order and uses the same fields, ISO dates, and nulls as the local export.

The API returns `400` for an empty file, `413` for a file over the size
limit, `415` for an unsupported extension or media type, and `422` for a missing
file, unreadable HTML, or a page without recognizable BARS subjects. Unexpected
parser failures return a generic `500` response.

## Parser architecture

`parse_file` reads the local file and hands the bytes to `parse_html`, which
uses Beautiful Soup to find each subject heading and its linked table.
The parser reads assessment rows and skips criteria, checkpoint, and summary
rows. It returns `Subject` and `Assessment` dataclasses with Python `date`
objects. `export_json` converts those objects to ISO date strings and writes
the results to disk.

The route in `backend/main.py` checks the upload and passes its bytes directly
to `parse_html`. FastAPI serializes the same dataclasses to JSON, so both
entry points share the parsing rules.

## Testing

Run the automated tests from the repository root with `python -m pytest`.
The parser and API tests use synthetic BARS markup and can run without the
private sample.
