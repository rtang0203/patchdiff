"""Validation errors — DIFF_SPEC section 2."""

import pytest

from conftest import PatchError, diff_patches, load_patch, write_csv, write_raw


def test_duplicate_column_names_error(tmp_path):
    with pytest.raises(PatchError):
        load_patch(write_csv(tmp_path, "p.csv", """
            BeginDate,EndDate,Issuer,Country,Country
            ,,JBL,USA,FRA
        """))


def test_column_name_with_surrounding_whitespace_errors(tmp_path):
    """Header names must match exactly rather than being silently repaired."""
    with pytest.raises(PatchError):
        load_patch(write_raw(
            tmp_path, "p.csv",
            "BeginDate,EndDate,Issuer,Country,Country \n,,JBL,USA,FRA\n"))


def test_blank_key_cell_errors(tmp_path):
    with pytest.raises(PatchError):
        load_patch(write_csv(tmp_path, "p.csv", """
            BeginDate,EndDate,Issuer,Country
            ,,JBL,USA
            ,,,FRA
        """))


def test_whitespace_only_key_cell_errors(tmp_path):
    """A required key containing only whitespace is still blank."""
    with pytest.raises(PatchError):
        load_patch(write_raw(
            tmp_path, "p.csv",
            "BeginDate,EndDate,Issuer,Country\n,,   ,FRA\n"))


def test_unparseable_date_errors(tmp_path):
    with pytest.raises(PatchError):
        load_patch(write_csv(tmp_path, "p.csv", """
            BeginDate,EndDate,Issuer,Country
            not-a-date,,JBL,USA
        """))


@pytest.mark.parametrize(
    ("header", "row", "missing"),
    [
        ("EndDate,Issuer,Country", ",JBL,USA", "BeginDate"),
        ("BeginDate,Issuer,Country", ",JBL,USA", "EndDate"),
    ],
)
def test_missing_required_date_column_errors(tmp_path, header, row, missing):
    path = write_raw(tmp_path, "p.csv", f"{header}\n{row}\n")
    with pytest.raises(PatchError, match=missing):
        load_patch(path)


def test_malformed_csv_errors(tmp_path):
    path = write_raw(
        tmp_path,
        "p.csv",
        'BeginDate,EndDate,Issuer,Country\n,,JBL,"USA\n',
    )
    with pytest.raises(PatchError, match="cannot read"):
        load_patch(path)


def test_invalid_utf8_errors(tmp_path):
    path = tmp_path / "p.csv"
    path.write_bytes(b"BeginDate,EndDate,Issuer,Country\n,,JBL,\xff\n")
    with pytest.raises(PatchError, match="cannot read"):
        load_patch(path)


def test_too_few_columns_errors(tmp_path):
    with pytest.raises(PatchError):
        load_patch(write_csv(tmp_path, "p.csv", """
            BeginDate,EndDate
            ,
        """))


def test_key_column_mismatch_errors(tmp_path):
    old = load_patch(write_csv(tmp_path, "old.csv", """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
    """))
    new = load_patch(write_csv(tmp_path, "new.csv", """
        BeginDate,EndDate,Ticker,Country
        ,,JBL,USA
    """))
    with pytest.raises(PatchError):
        diff_patches(old, new)


def test_reorder_promoting_different_column_to_key_errors(tmp_path):
    """Documented consequence of the positional key rule: this content is
    otherwise identical, but Country now sits in the key position."""
    old = load_patch(write_csv(tmp_path, "old.csv", """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
    """))
    new = load_patch(write_csv(tmp_path, "new.csv", """
        BeginDate,EndDate,Country,Issuer
        ,,USA,JBL
    """))
    with pytest.raises(PatchError):
        diff_patches(old, new)


def test_header_only_file_is_valid_and_empty(tmp_path):
    p = load_patch(write_csv(tmp_path, "p.csv", """
        BeginDate,EndDate,Issuer,Country
    """))
    assert p.rows == []


def test_two_header_only_files_have_no_diff(tmp_path):
    header = "BeginDate,EndDate,Issuer,Country\n"
    old = load_patch(write_raw(tmp_path, "old.csv", header))
    new = load_patch(write_raw(tmp_path, "new.csv", header))
    assert diff_patches(old, new).has_differences is False


def test_blank_column_name_errors(tmp_path):
    """Excel sometimes emits unnamed trailing columns. Rejected rather than
    repaired: a column with no name has no meaning in a patch."""
    with pytest.raises(PatchError):
        load_patch(write_raw(
            tmp_path, "p.csv",
            "BeginDate,EndDate,Issuer,Country,,\n,,JBL,USA,,\n"))


def test_ragged_row_errors(tmp_path):
    """A row with the wrong number of cells has values with no column to
    belong to. Rejected rather than padded or truncated."""
    with pytest.raises(PatchError):
        load_patch(write_raw(
            tmp_path, "p.csv",
            "BeginDate,EndDate,Issuer,Country\n,,JBL\n"))


def test_two_digit_year_errors(tmp_path):
    """Ambiguous: 2/1/24 could be 2024 or 1924."""
    with pytest.raises(PatchError):
        load_patch(write_csv(tmp_path, "p.csv", """
            BeginDate,EndDate,Issuer,Country
            2/1/24,,JBL,USA
        """))
