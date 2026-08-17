"""End-to-end expectations for the five provided sample patches.

The samples form a chain: 0 -> 1 -> 2 -> 3 -> 4, each step exercising one
feature. Patch3 -> Patch4 is the duplicate-key case the whole matching
algorithm exists to handle.
"""

import datetime as dt

import pytest

from conftest import changes_by_column, find_modification, keys, sample_diff


# --------------------------------------------------------------------------
# Patch0 -> Patch1 : two rows added
# --------------------------------------------------------------------------

def test_0_to_1_adds_two_rows():
    diff = sample_diff(0, 1)
    assert diff.columns_added == []
    assert diff.columns_removed == []
    assert diff.rows_modified == []
    assert diff.rows_removed == []
    assert keys(diff.rows_added) == ["FR", "PIPR"]
    assert len(diff.rows_unchanged) == 3


def test_0_to_1_added_fr_row_is_date_scoped():
    diff = sample_diff(0, 1)
    fr = next(row for row in diff.rows_added if row.key == "FR")
    assert fr.scope.begin == dt.date(2024, 2, 1)
    assert fr.scope.end is None
    assert {k: v for k, v in fr.values.items() if v} == {
        "Country": "FRA", "Conviction": "Low",
    }


def test_0_to_1_added_pipr_row_joins_an_existing_key():
    """PIPR already had an all-time row that matches exactly. The second row is
    an addition, not a modification of the first."""
    diff = sample_diff(0, 1)
    pipr = next(row for row in diff.rows_added if row.key == "PIPR")
    assert pipr.scope.begin is None
    assert {k: v for k, v in pipr.values.items() if v} == {
        "Country": "USA", "Conviction": "High",
    }


def test_1_reverse_diff_removes_the_same_two_rows():
    diff = sample_diff(1, 0)
    assert keys(diff.rows_removed) == ["FR", "PIPR"]
    assert diff.rows_added == []


# --------------------------------------------------------------------------
# Patch1 -> Patch2 : Analyst column added
# --------------------------------------------------------------------------

def test_1_to_2_adds_a_column_and_no_rows():
    diff = sample_diff(1, 2)
    assert diff.columns_added == ["Analyst"]
    assert diff.columns_removed == []
    assert diff.rows_modified == []
    assert diff.rows_added == []
    assert diff.rows_removed == []
    assert len(diff.rows_unchanged) == 5


def test_2_to_1_removes_the_column_without_row_noise():
    diff = sample_diff(2, 1)
    assert diff.columns_removed == ["Analyst"]
    assert diff.rows_modified == []


# --------------------------------------------------------------------------
# Patch2 -> Patch3 : columns reordered, IBM added
# --------------------------------------------------------------------------

def test_2_to_3_ignores_the_column_reorder():
    diff = sample_diff(2, 3)
    assert diff.columns_added == []
    assert diff.columns_removed == []


def test_2_to_3_reports_only_the_ibm_addition():
    diff = sample_diff(2, 3)
    assert keys(diff.rows_added) == ["IBM"]
    assert diff.rows_modified == []
    assert diff.rows_removed == []
    ibm = diff.rows_added[0]
    assert ibm.scope.begin == dt.date(2024, 3, 1)
    assert {k: v for k, v in ibm.values.items() if v} == {"Conviction": "Low"}


# --------------------------------------------------------------------------
# Patch3 -> Patch4 : the duplicate-key case
# --------------------------------------------------------------------------

def test_3_to_4_pipr_group_collapses_to_one_modification_and_one_removal():
    """Old PIPR rows: (Sector=CD, Country=FRA) and (Country=USA, Conviction=High).
    New PIPR row: (Sector=CD, Country=USA, Conviction=High).

    Distance to the first is 2, to the second is 1, so greedy pairs with the
    second and the first is reported removed."""
    diff = sample_diff(3, 4)
    m = find_modification(diff, "PIPR")
    assert changes_by_column(m) == {
        "Sector": ("", "Consumer Discretionary", "set")
    }
    removed = [row for row in diff.rows_removed if row.key == "PIPR"]
    assert len(removed) == 1
    assert removed[0].values["Country"] == "FRA"
    assert removed[0].values["Sector"] == "Consumer Discretionary"


def test_3_to_4_fr_analyst_changes():
    diff = sample_diff(3, 4)
    fr = find_modification(diff, "FR", begin=dt.date(2024, 2, 1))
    assert changes_by_column(fr) == {"Analyst": ("Bob", "Sally", "changed")}
    assert fr.scope_changed is False


def test_3_to_4_totals():
    diff = sample_diff(3, 4)
    assert diff.columns_added == []
    assert diff.columns_removed == []
    assert len(diff.rows_modified) == 2      # PIPR, FR
    assert len(diff.rows_removed) == 1       # PIPR
    assert diff.rows_added == []
    assert len(diff.rows_unchanged) == 3     # JBL, FR all-time, IBM


def test_3_to_4_jbl_and_ibm_untouched():
    diff = sample_diff(3, 4)
    unchanged = sorted(new_row.key for _, new_row in diff.rows_unchanged)
    assert unchanged == ["FR", "IBM", "JBL"]


# --------------------------------------------------------------------------
# Invariants across the whole sample set
# --------------------------------------------------------------------------

@pytest.mark.parametrize("n", [0, 1, 2, 3, 4])
def test_sample_diffed_against_itself_is_empty(n):
    assert sample_diff(n, n).has_differences is False


@pytest.mark.parametrize("a,b", [(0, 1), (1, 2), (2, 3), (3, 4), (0, 4)])
def test_every_row_is_accounted_for_exactly_once(a, b):
    """No row may be silently dropped or double-counted by the matcher."""
    from conftest import FIXTURES, load_patch
    old = load_patch(FIXTURES / f"Patch{a}.csv")
    new = load_patch(FIXTURES / f"Patch{b}.csv")
    diff = sample_diff(a, b)

    old_seen = (len(diff.rows_removed) + len(diff.rows_modified)
                + len(diff.rows_unchanged))
    new_seen = (len(diff.rows_added) + len(diff.rows_modified)
                + len(diff.rows_unchanged))
    assert old_seen == len(old.rows)
    assert new_seen == len(new.rows)


@pytest.mark.parametrize("a,b", [(0, 1), (1, 2), (2, 3), (3, 4)])
def test_reverse_diff_mirrors_counts(a, b):
    """Additions become removals and vice versa; modifications stay put."""
    fwd, rev = sample_diff(a, b), sample_diff(b, a)
    assert len(fwd.rows_added) == len(rev.rows_removed)
    assert len(fwd.rows_removed) == len(rev.rows_added)
    assert len(fwd.rows_modified) == len(rev.rows_modified)
    assert fwd.columns_added == rev.columns_removed


