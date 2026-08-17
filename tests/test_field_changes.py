"""Field-level change classification — DIFF_SPEC section 6.

A blank value column means "leave the existing value in the system alone", so
blank is not an empty string with no meaning — it is the absence of a rule.
Setting and clearing must be distinguishable from an ordinary value change.
"""

from conftest import changes_by_column, diff_text, find_modification


def test_blank_to_value_is_a_set(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Analyst
        ,,TSLA,
    """
    new = """
        BeginDate,EndDate,Issuer,Analyst
        ,,TSLA,Bob
    """
    m = find_modification(diff_text(tmp_path, old, new), "TSLA")
    assert changes_by_column(m) == {"Analyst": ("", "Bob", "set")}


def test_value_to_blank_is_a_clear(tmp_path):
    """The most consequential change a user can make: the patch silently stops
    touching a field. Must not render as 'changed from Bob to ""'."""
    old = """
        BeginDate,EndDate,Issuer,Analyst
        ,,TSLA,Bob
    """
    new = """
        BeginDate,EndDate,Issuer,Analyst
        ,,TSLA,
    """
    m = find_modification(diff_text(tmp_path, old, new), "TSLA")
    assert changes_by_column(m) == {"Analyst": ("Bob", "", "cleared")}


def test_value_to_different_value_is_a_change(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Analyst
        ,,MSFT,Bob
    """
    new = """
        BeginDate,EndDate,Issuer,Analyst
        ,,MSFT,Mike
    """
    m = find_modification(diff_text(tmp_path, old, new), "MSFT")
    assert changes_by_column(m) == {"Analyst": ("Bob", "Mike", "changed")}


def test_unchanged_fields_are_not_reported(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Country,Conviction,Sector
        ,,JBL,USA,High,Computers
    """
    new = """
        BeginDate,EndDate,Issuer,Country,Conviction,Sector
        ,,JBL,USA,Low,Computers
    """
    m = find_modification(diff_text(tmp_path, old, new), "JBL")
    assert [c.column for c in m.field_changes] == ["Conviction"]


def test_all_three_kinds_in_one_row(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Country,Conviction,Sector
        ,,JBL,USA,High,
    """
    new = """
        BeginDate,EndDate,Issuer,Country,Conviction,Sector
        ,,JBL,FRA,,Computers
    """
    m = find_modification(diff_text(tmp_path, old, new), "JBL")
    assert changes_by_column(m) == {
        "Country": ("USA", "FRA", "changed"),
        "Conviction": ("High", "", "cleared"),
        "Sector": ("", "Computers", "set"),
    }


def test_case_change_is_a_real_change(tmp_path):
    """Whitespace is normalized; case is not. 'bob' and 'Bob' are different
    values as far as the system applying the patch is concerned."""
    old = """
        BeginDate,EndDate,Issuer,Analyst
        ,,MSFT,Bob
    """
    new = """
        BeginDate,EndDate,Issuer,Analyst
        ,,MSFT,bob
    """
    assert diff_text(tmp_path, old, new).has_differences is True


def test_added_and_removed_rows_list_only_populated_columns(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Country,Conviction,Sector
        ,,JBL,USA,,
    """
    new = """
        BeginDate,EndDate,Issuer,Country,Conviction,Sector
        ,,JBL,USA,,
        20240301,,IBM,,Low,
    """
    diff = diff_text(tmp_path, old, new)
    added = diff.rows_added[0]
    populated = {k: v for k, v in added.values.items() if v}
    assert populated == {"Conviction": "Low"}
