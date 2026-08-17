"""Parsing and normalization — DIFF_SPEC section 1.

The theme of this module: two files that differ only in *encoding* should
produce no diff. Every test here is a way a file can look different on disk
while describing the same patch.
"""

import datetime as dt

from conftest import diff_text, load_patch, write_csv, write_raw


# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------

def test_key_column_is_first_non_date_column(tmp_path):
    p = load_patch(write_csv(tmp_path, "p.csv", """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
    """))
    assert p.key_column == "Issuer"
    assert p.value_columns == ["Country"]


def test_key_column_found_when_dates_are_not_leading(tmp_path):
    """The assignment's prose example puts Issuer first; the sample files put
    the dates first. The rule is positional over non-date columns, not 'column 0'."""
    p = load_patch(write_csv(tmp_path, "p.csv", """
        Issuer,BeginDate,EndDate,Country
        JBL,,,USA
    """))
    assert p.key_column == "Issuer"


def test_line_numbers_are_one_based_and_count_the_header(tmp_path):
    p = load_patch(write_csv(tmp_path, "p.csv", """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
        ,,PIPR,FRA
    """))
    assert [r.line_number for r in p.rows] == [2, 3]


def test_blank_cells_are_empty_strings_not_none(tmp_path):
    p = load_patch(write_csv(tmp_path, "p.csv", """
        BeginDate,EndDate,Issuer,Country,Sector
        ,,JBL,USA,
    """))
    assert p.rows[0].values["Sector"] == ""
    assert p.rows[0].scope.begin is None
    assert p.rows[0].scope.end is None


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

def test_compact_date_format_parsed(tmp_path):
    """The sample patches use YYYYMMDD, the assignment prose uses M/D/YYYY."""
    p = load_patch(write_csv(tmp_path, "p.csv", """
        BeginDate,EndDate,Issuer,Country
        20240201,,FR,FRA
    """))
    assert p.rows[0].scope.begin == dt.date(2024, 2, 1)


def test_date_formats_are_equivalent(tmp_path):
    """Equivalent accepted date formats do not produce a change."""
    old = """
        BeginDate,EndDate,Issuer,Country
        20240201,20241231,FR,FRA
    """
    new = """
        BeginDate,EndDate,Issuer,Country
        2/1/2024,12/31/2024,FR,FRA
    """
    assert diff_text(tmp_path, old, new).has_differences is False


def test_iso_date_format_parsed(tmp_path):
    p = load_patch(write_csv(tmp_path, "p.csv", """
        BeginDate,EndDate,Issuer,Country
        2024-02-01,,FR,FRA
    """))
    assert p.rows[0].scope.begin == dt.date(2024, 2, 1)


# --------------------------------------------------------------------------
# Excel artifacts
# --------------------------------------------------------------------------

def test_utf8_bom_does_not_corrupt_first_header(tmp_path):
    """Excel writes UTF-8 CSVs with a BOM. Without utf-8-sig the first header
    becomes '\\ufeffBeginDate' and every column reads as removed + re-added."""
    body = "BeginDate,EndDate,Issuer,Country\n,,JBL,USA\n"
    old = load_patch(write_raw(tmp_path, "old.csv", body))
    new = load_patch(write_raw(tmp_path, "new.csv", body, encoding="utf-8-sig"))
    assert new.key_column == "Issuer"
    from conftest import diff_patches
    assert diff_patches(old, new).has_differences is False


def test_header_whitespace_is_stripped(tmp_path):
    old = write_raw(tmp_path, "old.csv",
                    "BeginDate,EndDate,Issuer,Country\n,,JBL,USA\n")
    new = write_raw(tmp_path, "new.csv",
                    "BeginDate , EndDate ,Issuer , Country \n,,JBL,USA\n")
    from conftest import diff_patches
    assert diff_patches(load_patch(old), load_patch(new)).has_differences is False


def test_cell_whitespace_is_stripped(tmp_path):
    old = write_raw(tmp_path, "old.csv",
                    "BeginDate,EndDate,Issuer,Country\n,,JBL,USA\n")
    new = write_raw(tmp_path, "new.csv",
                    "BeginDate,EndDate,Issuer,Country\n,, JBL , USA \n")
    from conftest import diff_patches
    assert diff_patches(load_patch(old), load_patch(new)).has_differences is False


def test_trailing_blank_lines_are_skipped(tmp_path):
    """A stray newline yields [] from csv.reader and would otherwise trip the
    blank-key validation on a perfectly valid file."""
    p = load_patch(write_raw(
        tmp_path, "p.csv",
        "BeginDate,EndDate,Issuer,Country\n,,JBL,USA\n\n\n"))
    assert len(p.rows) == 1


def test_all_blank_row_is_skipped(tmp_path):
    p = load_patch(write_raw(
        tmp_path, "p.csv",
        "BeginDate,EndDate,Issuer,Country\n,,JBL,USA\n,,,\n"))
    assert len(p.rows) == 1


