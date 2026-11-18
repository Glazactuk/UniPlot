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
- pytest

## Installation

Use Python 3.12 or newer. From the repository root, install the dependencies
with `python -m pip install -r requirements.txt`.

## Usage

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

## Parser architecture

`parse_file` reads the local file and hands the bytes to `parse_html`, which
uses Beautiful Soup to find each subject heading and its linked table.
The parser reads assessment rows and skips criteria, checkpoint, and summary
rows. It returns `Subject` and `Assessment` dataclasses with Python `date`
objects. `export_json` converts those objects to ISO date strings and writes
the results to disk.

## Testing

Run the automated tests from the repository root with `python -m pytest`.
The tests use synthetic BARS markup and can run without the private sample.
