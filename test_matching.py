"""Row grouping and matching — DIFF_SPEC sections 4 and 5.

The heart of the implementation. Duplicate keys are the hard case and the
sample patches contain them, so most of this module is about groups with more
than one row per side.
"""

import datetime as dt

from conftest import changes_by_column, diff_text, find_modification, keys


# --------------------------------------------------------------------------
# Row order is meaningless
# --------------------------------------------------------------------------

def test_row_reorder_produces_no_diff(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
        ,,PIPR,FRA
        ,,FR,USA
    """
    new = """
        BeginDate,EndDate,Issuer,Country
        ,,FR,USA
        ,,JBL,USA
        ,,PIPR,FRA
    """
    assert diff_text(tmp_path, old, new).has_differences is False


def test_reorder_within_a_duplicate_key_group_produces_no_diff(tmp_path):
    """This is why matching within a group cannot be by ordinal position."""
    old = """
        BeginDate,EndDate,Issuer,Country,Conviction
        ,,PIPR,FRA,
        ,,PIPR,USA,High
    """
    new = """
        BeginDate,EndDate,Issuer,Country,Conviction
        ,,PIPR,USA,High
        ,,PIPR,FRA,
    """
    assert diff_text(tmp_path, old, new).has_differences is False


# --------------------------------------------------------------------------
# Stage 1 — exact
# --------------------------------------------------------------------------

def test_identical_files_have_no_diff(tmp_path):
    text = """
        BeginDate,EndDate,Issuer,Country,Sector
        ,,JBL,USA,Computers
        20240201,20241231,FR,FRA,
    """
    diff = diff_text(tmp_path, text, text)
    assert diff.has_differences is False
    assert len(diff.rows_unchanged) == 2


def test_two_identical_duplicate_rows_pair_off(tmp_path):
    text = """
        BeginDate,EndDate,Issuer,Country
        ,,PIPR,FRA
        ,,PIPR,FRA
    """
    diff = diff_text(tmp_path, text, text)
    assert diff.has_differences is False
    assert len(diff.rows_unchanged) == 2


# --------------------------------------------------------------------------
# Stage 2 — same scope, different values
# --------------------------------------------------------------------------

def test_single_field_change_is_a_modification(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Analyst
        ,,MSFT,Bob
    """
    new = """
        BeginDate,EndDate,Issuer,Analyst
        ,,MSFT,Mike
    """
    diff = diff_text(tmp_path, old, new)
    m = find_modification(diff, "MSFT")
    assert changes_by_column(m) == {"Analyst": ("Bob", "Mike", "changed")}


def test_every_field_changing_is_still_a_modification(tmp_path):
    """1-vs-1 groups are always modifications. No distance threshold."""
    old = """
        BeginDate,EndDate,Issuer,Country,Conviction,Sector
        ,,JBL,USA,High,Computers
    """
    new = """
        BeginDate,EndDate,Issuer,Country,Conviction,Sector
        ,,JBL,FRA,Low,Real Estate
    """
    diff = diff_text(tmp_path, old, new)
    assert diff.rows_added == []
    assert diff.rows_removed == []
    assert len(find_modification(diff, "JBL").field_changes) == 3


# --------------------------------------------------------------------------
# Stage 3 — same values, different scope
# --------------------------------------------------------------------------

def test_end_date_change_is_a_modification_not_delete_plus_add(tmp_path):
    """The case that forced grouping on key alone rather than key + scope."""
    old = """
        BeginDate,EndDate,Issuer,Analyst
        20240101,20240131,AMT,Bob
    """
    new = """
        BeginDate,EndDate,Issuer,Analyst
        20240101,20240229,AMT,Bob
    """
    diff = diff_text(tmp_path, old, new)
    assert diff.rows_added == []
    assert diff.rows_removed == []
    m = find_modification(diff, "AMT")
    assert m.scope_changed is True
    assert m.field_changes == ()
    assert m.old_row.scope.end == dt.date(2024, 1, 31)
    assert m.new_row.scope.end == dt.date(2024, 2, 29)


def test_scope_and_values_can_both_change(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Analyst
        20240101,,AMT,Bob
    """
    new = """
        BeginDate,EndDate,Issuer,Analyst
        20240301,,AMT,Sally
    """
    m = find_modification(diff_text(tmp_path, old, new), "AMT")
    assert m.scope_changed is True
    assert changes_by_column(m) == {"Analyst": ("Bob", "Sally", "changed")}


def test_scope_match_preferred_over_value_match(tmp_path):
    """Stage 2 runs before stage 3. The row keeping its scope is the better
    pairing even though the other row keeps its values."""
    old = """
        BeginDate,EndDate,Issuer,Country
        20240101,,FR,USA
        20240601,,FR,FRA
    """
    new = """
        BeginDate,EndDate,Issuer,Country
        20240101,,FR,FRA
        20240601,,FR,ITA
    """
    diff = diff_text(tmp_path, old, new)
    assert diff.rows_added == []
    assert diff.rows_removed == []
    jan = find_modification(diff, "FR", begin=dt.date(2024, 1, 1))
    assert jan.scope_changed is False
    assert changes_by_column(jan) == {"Country": ("USA", "FRA", "changed")}


# --------------------------------------------------------------------------
# Additions and removals
# --------------------------------------------------------------------------

def test_new_key_is_an_addition(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
    """
    new = """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
        20240301,,IBM,FRA
    """
    diff = diff_text(tmp_path, old, new)
    assert keys(diff.rows_added) == ["IBM"]
    assert diff.rows_modified == []


def test_removed_key_is_a_removal(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
        ,,PIPR,FRA
    """
    new = """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
    """
    diff = diff_text(tmp_path, old, new)
    assert keys(diff.rows_removed) == ["PIPR"]
    assert diff.rows_modified == []


def test_extra_row_in_group_with_exact_match_is_an_addition(tmp_path):
    """Stage 1 consumes the identical pair, leaving the new row unmatched."""
    old = """
        BeginDate,EndDate,Issuer,Country,Conviction
        ,,PIPR,FRA,
    """
    new = """
        BeginDate,EndDate,Issuer,Country,Conviction
        ,,PIPR,FRA,
        ,,PIPR,USA,High
    """
    diff = diff_text(tmp_path, old, new)
    assert diff.rows_modified == []
    assert len(diff.rows_added) == 1
    assert diff.rows_added[0].row.values["Conviction"] == "High"


# --------------------------------------------------------------------------
# Greedy pairing in ambiguous groups
# --------------------------------------------------------------------------

def test_greedy_picks_the_closest_candidate(tmp_path):
    """Two old rows, one new row, all same scope. The new row is 1 field from
    row B and 2 fields from row A, so it pairs with B and A is removed."""
    old = """
        BeginDate,EndDate,Issuer,Sector,Country,Conviction
        ,,PIPR,Consumer Discretionary,FRA,
        ,,PIPR,,USA,High
    """
    new = """
        BeginDate,EndDate,Issuer,Sector,Country,Conviction
        ,,PIPR,Consumer Discretionary,USA,High
    """
    diff = diff_text(tmp_path, old, new)
    m = find_modification(diff, "PIPR")
    assert changes_by_column(m) == {
        "Sector": ("", "Consumer Discretionary", "set")
    }
    assert len(diff.rows_removed) == 1
    assert diff.rows_removed[0].row.values["Country"] == "FRA"


def test_greedy_is_stable_regardless_of_input_row_order(tmp_path):
    """Same group, old rows swapped. Must reach the same pairing."""
    old_a = """
        BeginDate,EndDate,Issuer,Sector,Country,Conviction
        ,,PIPR,Consumer Discretionary,FRA,
        ,,PIPR,,USA,High
    """
    old_b = """
        BeginDate,EndDate,Issuer,Sector,Country,Conviction
        ,,PIPR,,USA,High
        ,,PIPR,Consumer Discretionary,FRA,
    """
    new = """
        BeginDate,EndDate,Issuer,Sector,Country,Conviction
        ,,PIPR,Consumer Discretionary,USA,High
    """
    a = diff_text(tmp_path, old_a, new)
    b = diff_text(tmp_path, old_b, new)
    assert changes_by_column(find_modification(a, "PIPR")) == \
           changes_by_column(find_modification(b, "PIPR"))
    assert a.rows_removed[0].row.values == b.rows_removed[0].row.values


def test_tie_broken_by_line_number(tmp_path):
    """Both old rows are equidistant from the new row. The lower old line
    number wins, so the pairing is deterministic rather than dict-order."""
    old = """
        BeginDate,EndDate,Issuer,Country
        ,,PIPR,FRA
        ,,PIPR,ITA
    """
    new = """
        BeginDate,EndDate,Issuer,Country
        ,,PIPR,USA
    """
    diff = diff_text(tmp_path, old, new)
    m = find_modification(diff, "PIPR")
    assert m.old_row.line_number == 2
    assert changes_by_column(m) == {"Country": ("FRA", "USA", "changed")}
    assert diff.rows_removed[0].row.values["Country"] == "ITA"


def test_many_to_many_group(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Country,Conviction
        ,,PIPR,USA,High
        20240101,,PIPR,FRA,Low
        20240601,,PIPR,ITA,
    """
    new = """
        BeginDate,EndDate,Issuer,Country,Conviction
        ,,PIPR,USA,Low
        20240101,,PIPR,FRA,Low
        20241201,,PIPR,DEU,
    """
    diff = diff_text(tmp_path, old, new)
    assert len(diff.rows_unchanged) == 1      # the 20240101 row
    assert len(diff.rows_modified) == 2       # all-time (Conviction), and the last row
    assert diff.rows_added == []
    assert diff.rows_removed == []


def test_groups_are_independent(tmp_path):
    """A row must never match across keys, however similar it looks."""
    old = """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
    """
    new = """
        BeginDate,EndDate,Issuer,Country
        ,,PIPR,USA
    """
    diff = diff_text(tmp_path, old, new)
    assert diff.rows_modified == []
    assert keys(diff.rows_added) == ["PIPR"]
    assert keys(diff.rows_removed) == ["JBL"]
