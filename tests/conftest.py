"""Shared fixtures and helpers for the patch diff test suite.

API CONTRACT
============
These tests are written against the surface below. If you name things
differently, adjust the imports in this file only — the test modules go
through the helpers here rather than importing the package directly.

    load_patch(path) -> Patch
        .key_column      str
        .value_columns   list[str]        (declaration order; identity is set-based)
        .rows            list[PatchRow]

    PatchRow
        .key             str
        .scope.begin      datetime.date | None
        .scope.end        datetime.date | None
        .values          dict[str, str]   (blank cells present as "")
        .line_number     int              (1-based, from the source file)

    diff_patches(old: Patch, new: Patch) -> PatchDiff
        .columns_added   list[str]
        .columns_removed list[str]
        .rows_added      list[PatchRow]
        .rows_removed    list[PatchRow]
        .rows_modified   list[RowModification]
        .rows_unchanged  list[(old_row, new_row)]
        .has_differences bool

    RowModification
        .key             str
        .old_row         PatchRow
        .new_row         PatchRow
        .scope_changed   bool
        .field_changes   list[FieldChange]

    FieldChange
        .column          str
        .old_value       str
        .new_value       str
        .kind            "set" | "cleared" | "changed"

    render(diff: PatchDiff) -> str

    PatchError  — raised for every condition in DIFF_SPEC section 2.
"""

import datetime as dt
from pathlib import Path

import pytest

from patchdiff import PatchError, diff_patches, load_patch, render  # noqa: F401

FIXTURES = Path(__file__).parent / "fixtures"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def write_csv(tmp_path, name, text):
    """Write a CSV from an inline string. Leading newline and indentation are
    stripped so tests can use readable triple-quoted literals."""
    lines = [ln.strip() for ln in text.strip("\n").split("\n")]
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_raw(tmp_path, name, text, encoding="utf-8"):
    """Write bytes-exact content — for BOM, whitespace and blank-line tests."""
    path = tmp_path / name
    path.write_text(text, encoding=encoding)
    return path


def diff_text(tmp_path, old_text, new_text):
    """Diff two inline CSVs. Returns a PatchDiff."""
    old = load_patch(write_csv(tmp_path, "old.csv", old_text))
    new = load_patch(write_csv(tmp_path, "new.csv", new_text))
    return diff_patches(old, new)


def sample_diff(a, b):
    """Diff two of the provided sample patches by number."""
    return diff_patches(
        load_patch(FIXTURES / f"Patch{a}.csv"),
        load_patch(FIXTURES / f"Patch{b}.csv"),
    )


def keys(entries):
    """Sorted key values from additions, removals or modifications."""
    return sorted(e.key for e in entries)


def changes_by_column(modification):
    """{column: (old, new, kind)} for a RowModification."""
    return {
        c.column: (c.old_value, c.new_value, c.kind)
        for c in modification.field_changes
    }


def find_modification(diff, key, begin=None):
    """Single modification for a key, optionally disambiguated by begin date."""
    hits = [
        m for m in diff.rows_modified
        if m.key == key and (begin is None or m.new_row.scope.begin == begin)
    ]
    assert len(hits) == 1, f"expected 1 modification for {key}, got {len(hits)}"
    return hits[0]


# --------------------------------------------------------------------------
# Common inline patches
# --------------------------------------------------------------------------

BASE = """
BeginDate,EndDate,Issuer,Country,Conviction,Sector
,,JBL,USA,,Computers
,,PIPR,FRA,,Consumer Discretionary
"""


@pytest.fixture
def d():
    return dt.date
