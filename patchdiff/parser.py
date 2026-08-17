"""Reading patch CSVs into the model.

Handles the encoding and date formats used by the supplied Excel/CSV examples,
then rejects input it cannot interpret rather than repairing it. After this
layer, comparison is naive.
"""

import csv
from datetime import datetime

from .model import WELL_KNOWN_COLUMNS, Patch, PatchError, PatchRow, Scope

# Tried in order. The sample patches use YYYYMMDD; the assignment's prose
# examples use M/D/YYYY. Two-digit years are ambiguous and rejected.
DATE_FORMATS = ("%Y%m%d", "%m/%d/%Y", "%Y-%m-%d")


def load_patch(path) -> Patch:
    """Parse a patch CSV. Raises PatchError on anything malformed."""
    header, records = _read(path)
    _validate_header(header, path)
    key_column, value_columns = _classify(header, path)
    index = {name: i for i, name in enumerate(header)}
    return Patch(
        key_column=key_column,
        value_columns=value_columns,
        rows=[_build_row(cells, n, index, key_column, value_columns, path)
              for n, cells in records],
    )


def _read(path):
    """Return (header, [(line_number, cells)]), preserving cell contents.

    utf-8-sig matters: Excel writes a BOM, and without stripping it the first
    header becomes '\\ufeffBeginDate', so two identical files report every
    column as removed and re-added.
    """
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh, strict=True)
            records = [(reader.line_num, cells) for cells in reader]
    except (OSError, UnicodeError, csv.Error) as exc:
        raise PatchError(f"cannot read {path}: {exc}") from exc

    # A physical blank line is not a patch row. A comma-filled record is kept
    # and rejected below as a row with a blank key.
    records = [(n, cells) for n, cells in records if cells]
    if not records:
        raise PatchError(f"{path} is empty")

    header, rows = records[0][1], records[1:]
    for n, cells in rows:
        if len(cells) != len(header):
            raise PatchError(f"{path} line {n}: expected {len(header)} columns, "
                             f"found {len(cells)}")
    return header, rows


def _validate_header(header, path):
    if len(header) < 3:
        raise PatchError(f"{path}: expected BeginDate, EndDate and a key "
                         f"column, found {header}")
    if not all(header):
        raise PatchError(f"{path}: blank column name in header {header}")
    padded = [c for c in header if c != c.strip()]
    if padded:
        raise PatchError(
            f"{path}: column name(s) contain surrounding whitespace {padded}"
        )
    duplicates = sorted({c for c in header if header.count(c) > 1})
    if duplicates:
        raise PatchError(f"{path}: duplicate column name(s) {duplicates}")
    missing = [c for c in WELL_KNOWN_COLUMNS if c not in header]
    if missing:
        raise PatchError(f"{path}: missing required column(s) {missing}")


def _classify(header, path):
    """Key column is the first column that is not BeginDate/EndDate.

    Positional, as the assignment specifies -- which is why reordering columns
    so a different one lands first is an error rather than a no-op.
    """
    key_column, value_columns = None, []
    for name in header:
        if name in WELL_KNOWN_COLUMNS:
            continue
        if key_column is None:
            key_column = name
        else:
            value_columns.append(name)
    if key_column is None:
        raise PatchError(f"{path}: no key column; every column is a date column")
    return key_column, value_columns


def _build_row(cells, line_no, index, key_column, value_columns, path):
    key = cells[index[key_column]]
    if not key.strip():
        raise PatchError(f"{path} line {line_no}: blank {key_column}")
    scope = Scope(begin=_parse_date(cells, index, "BeginDate", line_no, path),
                  end=_parse_date(cells, index, "EndDate", line_no, path))
    return PatchRow(key=key, scope=scope, line_number=line_no,
                    values={c: cells[index[c]] for c in value_columns})


def _parse_date(cells, index, column, line_no, path):
    raw = cells[index[column]]
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise PatchError(f"{path} line {line_no}: cannot parse {column} {raw!r}")
