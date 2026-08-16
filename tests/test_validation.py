"""Validation errors — DIFF_SPEC section 2."""

import pytest

from conftest import PatchError, diff_patches, load_patch, write_csv, write_raw


def test_duplicate_column_names_error(tmp_path):
    with pytest.raises(PatchError):
        load_patch(write_csv(tmp_path, "p.csv", """
            BeginDate,EndDate,Issuer,Country,Country
            ,,JBL,USA,FRA
        """))


def test_duplicate_column_names_after_stripping_error(tmp_path):
    """'Country ' and 'Country' collide once normalized."""
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
    """Blank after stripping is still blank — but the row is not *wholly*
    empty, so it must not be silently skipped either."""
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
    assert p.rows == ()


def test_two_header_only_files_have_no_diff(tmp_path):
    header = "BeginDate,EndDate,Issuer,Country\n"
    old = load_patch(write_raw(tmp_path, "old.csv", header))
    new = load_patch(write_raw(tmp_path, "new.csv", header))
    assert diff_patches(old, new).has_differences is False
