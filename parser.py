"""Reading patch CSVs into the model.

Everything that makes two byte-different files mean the same thing is
normalized here: BOM, whitespace, date format, blank lines, trailing empty
columns. After this layer, comparison can be naive.
"""

import csv
from datetime import datetime

from .model import WELL_KNOWN_COLUMNS, Patch, PatchError, PatchRow, Scope

# Tried in order. The sample patches use YYYYMMDD; the assignment's prose
# examples use M/D/YYYY.
DATE_FORMATS = ("%Y%m%d", "%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y")


def load_patch(path) -> Patch:
    """Parse a patch CSV. Raises PatchError on anything malformed."""
    header, data_rows = _read_rows(path)
    header, data_rows = _drop_trailing_empty_columns(header, data_rows)
    _validate_header(header, path)

    key_column, value_columns = _classify_columns(header)
    index = {name: i for i, name in enumerate(header)}

    rows = tuple(
        _build_row(cells, line_no, index, key_column, value_columns, path)
        for line_no, cells in data_rows
    )
    return Patch(key_column=key_column, value_columns=value_columns, rows=rows)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _read_rows(path):
    """Return (header, [(line_number, cells), ...]) with everything stripped.

    utf-8-sig matters: Excel writes CSVs with a BOM, and without stripping it
    the first header becomes '\\ufeffBeginDate', which makes every column look
    removed and re-added on two otherwise identical files.
    """
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            records = [(reader.line_num, [c.strip() for c in cells])
                       for cells in reader]
    except OSError as exc:
        raise PatchError(f"cannot read {path}: {exc}") from exc

    # Drop wholly-empty records. A trailing newline yields [] from csv.reader
    # and would otherwise trip the blank-key check on a valid file.
    records = [(n, cells) for n, cells in records if any(cells)]
    if not records:
        raise PatchError(f"{path} is empty")

    header = records[0][1]
    # Pad short rows so column indexing is total. Extra cells beyond the header
    # are dropped; a row longer than the header is malformed Excel output and
    # the extra values have no column to belong to.
    data = [(n, (cells + [""] * len(header))[:len(header)])
            for n, cells in records[1:]]
    return header, data


def _drop_trailing_empty_columns(header, data_rows):
    """Excel exports sometimes carry unnamed trailing columns. Two of them
    would trip the duplicate-name check on a perfectly valid file."""
    width = len(header)
    while width and not header[width - 1] and all(
        not cells[width - 1] for _, cells in data_rows
    ):
        width -= 1
    return header[:width], [(n, cells[:width]) for n, cells in data_rows]


# ---------------------------------------------------------------------------
# Validation and classification
# ---------------------------------------------------------------------------

def _validate_header(header, path):
    if len(header) < 3:
        raise PatchError(
            f"{path}: expected at least BeginDate, EndDate and a key column, "
            f"found {header}"
        )
    seen = set()
    for name in header:
        if name in seen:
            raise PatchError(f"{path}: duplicate column {name!r}")
        seen.add(name)


def _classify_columns(header):
    """Key column is the first column that is not BeginDate/EndDate.

    Positional, as the assignment specifies — which is why reordering columns
    so a different column lands first is an error rather than a no-op. See
    DIFF_SPEC section 2.
    """
    key_column = None
    value_columns = []
    for name in header:
        if name in WELL_KNOWN_COLUMNS:
            continue
        if key_column is None:
            key_column = name
        else:
            value_columns.append(name)
    if key_column is None:
        raise PatchError("no key column: every column is BeginDate/EndDate")
    return key_column, tuple(value_columns)


def _build_row(cells, line_no, index, key_column, value_columns, path):
    key = cells[index[key_column]]
    if not key:
        raise PatchError(f"{path} line {line_no}: blank {key_column}")

    scope = Scope(
        begin=_parse_date(cells, index, "BeginDate", line_no, path),
        end=_parse_date(cells, index, "EndDate", line_no, path),
    )
    values = {c: cells[index[c]] for c in value_columns}
    return PatchRow(key=key, scope=scope, values=values, line_number=line_no)


def _parse_date(cells, index, column, line_no, path):
    if column not in index:
        return None          # missing date columns are out of scope, not an error
    raw = cells[index[column]]
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise PatchError(f"{path} line {line_no}: cannot parse {column} {raw!r}")
