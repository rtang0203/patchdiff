"""Column diff — DIFF_SPEC section 3.

Core invariant of this module: a column-level change never produces row-level
noise. Added and removed columns are reported once and excluded from matching.
"""

from conftest import diff_text


def test_column_reorder_produces_no_diff(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Country,Conviction,Sector
        ,,JBL,USA,High,Computers
    """
    new = """
        BeginDate,EndDate,Issuer,Sector,Country,Conviction
        ,,JBL,Computers,USA,High
    """
    assert diff_text(tmp_path, old, new).has_differences is False


def test_date_columns_may_move_too(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Country
        20240101,,JBL,USA
    """
    new = """
        Issuer,BeginDate,EndDate,Country
        JBL,20240101,,USA
    """
    assert diff_text(tmp_path, old, new).has_differences is False


def test_added_column_reported_once(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
        ,,PIPR,FRA
    """
    new = """
        BeginDate,EndDate,Issuer,Country,Analyst
        ,,JBL,USA,Bob
        ,,PIPR,FRA,Sally
    """
    diff = diff_text(tmp_path, old, new)
    assert diff.columns_added == ["Analyst"]
    assert diff.rows_modified == []
    assert diff.rows_added == []
    assert diff.rows_removed == []


def test_removed_column_reported_once(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Country,Sector
        ,,JBL,USA,Computers
        ,,PIPR,FRA,Consumer Discretionary
    """
    new = """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
        ,,PIPR,FRA
    """
    diff = diff_text(tmp_path, old, new)
    assert diff.columns_removed == ["Sector"]
    assert diff.rows_modified == []


def test_added_column_does_not_affect_matching(tmp_path):
    """The added column must be excluded before distance is computed, or it
    inflates every candidate pair's distance and can flip a greedy choice."""
    old = """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
    """
    new = """
        BeginDate,EndDate,Issuer,Country,Analyst
        ,,JBL,FRA,Bob
    """
    diff = diff_text(tmp_path, old, new)
    assert len(diff.rows_modified) == 1
    cols = [c.column for c in diff.rows_modified[0].field_changes]
    assert cols == ["Country"], "Analyst is a column change, not a field change"


def test_all_blank_added_column_has_no_row_effect(tmp_path):
    """Industry is blank throughout the provided samples — likely deliberate."""
    old = """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
    """
    new = """
        BeginDate,EndDate,Issuer,Country,Industry
        ,,JBL,USA,
    """
    diff = diff_text(tmp_path, old, new)
    assert diff.columns_added == ["Industry"]
    assert diff.rows_modified == []
    assert diff.rows_added == []


def test_all_blank_removed_column_has_no_row_effect(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Country,Industry
        ,,JBL,USA,
    """
    new = """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
    """
    diff = diff_text(tmp_path, old, new)
    assert diff.columns_removed == ["Industry"]
    assert diff.rows_modified == []


def test_column_swap_is_add_plus_remove(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Sector
        ,,JBL,Computers
    """
    new = """
        BeginDate,EndDate,Issuer,Industry
        ,,JBL,Computers
    """
    diff = diff_text(tmp_path, old, new)
    assert diff.columns_added == ["Industry"]
    assert diff.columns_removed == ["Sector"]
    assert diff.rows_modified == []


def test_column_change_alongside_row_change(tmp_path):
    """Both kinds of change in one diff, kept in their own sections."""
    old = """
        BeginDate,EndDate,Issuer,Country,Sector
        ,,JBL,USA,Computers
    """
    new = """
        BeginDate,EndDate,Issuer,Country,Analyst
        ,,JBL,FRA,Bob
    """
    diff = diff_text(tmp_path, old, new)
    assert diff.columns_added == ["Analyst"]
    assert diff.columns_removed == ["Sector"]
    assert len(diff.rows_modified) == 1
    assert [c.column for c in diff.rows_modified[0].field_changes] == ["Country"]
