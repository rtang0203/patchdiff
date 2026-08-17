"""Rendering, ordering and CLI behaviour — DIFF_SPEC sections 7, 8, 10.

These assert on shape and invariants rather than exact wording, so the prose
can be tuned without rewriting the suite. Add golden-file tests once the
wording settles.
"""

import re
import subprocess
import sys

from conftest import FIXTURES, diff_text, render, sample_diff


# --------------------------------------------------------------------------
# Determinism and ordering
# --------------------------------------------------------------------------



def test_output_is_independent_of_input_row_order(tmp_path):
    """Row order is meaningless, so output cannot be in file order — the
    renderer must sort. Two shuffles of the same patch must render identically."""
    base = """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
    """
    new_a = """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
        ,,AAPL,USA
        20240301,,IBM,FRA
    """
    new_b = """
        BeginDate,EndDate,Issuer,Country
        20240301,,IBM,FRA
        ,,JBL,USA
        ,,AAPL,USA
    """
    strip = lambda t: re.sub(r"\(lines? [^)]*\)", "", t)
    assert strip(render(diff_text(tmp_path, base, new_a))) == \
           strip(render(diff_text(tmp_path, base, new_b)))


def test_rows_render_in_key_then_scope_order(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Country
        ,,ZZZ,USA
    """
    new = """
        BeginDate,EndDate,Issuer,Country
        ,,ZZZ,USA
        20240601,,AAA,USA
        20240101,,AAA,USA
        ,,AAA,USA
    """
    out = render(diff_text(tmp_path, old, new))
    positions = [out.index(s) for s in ("all time", "2024-01-01", "2024-06-01")]
    assert positions == sorted(positions), "unscoped rows sort first, then by date"


# --------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------

def test_summary_appears_first():
    out = render(sample_diff(3, 4))
    head = out[:out.index("PIPR")]
    assert re.search(r"\b1\b.*removed|removed.*\b1\b", head, re.I)


def test_empty_sections_are_omitted():
    out = render(sample_diff(1, 2))   # column change only
    assert "Analyst" in out
    assert not re.search(r"^\s*(Added|Removed|Modified) rows", out, re.M)


def test_no_diff_renders_a_clear_statement(tmp_path):
    text = """
        BeginDate,EndDate,Issuer,Country
        ,,JBL,USA
    """
    out = render(diff_text(tmp_path, text, text))
    assert re.search(r"no (differences|changes)", out, re.I)


def test_dates_render_canonically_not_as_written():
    """Input is 20240201; output must not echo that back."""
    out = render(sample_diff(0, 1))
    assert "2024-02-01" in out
    assert "20240201" not in out


def test_newly_populated_field_renders_as_now_set(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Analyst
        ,,TSLA,
    """
    new = """
        BeginDate,EndDate,Issuer,Analyst
        ,,TSLA,Bob
    """
    out = render(diff_text(tmp_path, old, new))
    assert "Now sets Analyst to Bob (previously not set)" in out


def test_cleared_field_renders_as_no_longer_set(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Analyst
        ,,TSLA,Bob
    """
    new = """
        BeginDate,EndDate,Issuer,Analyst
        ,,TSLA,
    """
    out = render(diff_text(tmp_path, old, new))
    assert "No longer sets Analyst (previously set to Bob)" in out


def test_scope_change_is_visible_in_output(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Analyst
        20240101,20240131,AMT,Bob
    """
    new = """
        BeginDate,EndDate,Issuer,Analyst
        20240101,20240229,AMT,Bob
    """
    out = render(diff_text(tmp_path, old, new))
    assert "2024-01-31" in out and "2024-02-29" in out


def test_added_row_does_not_mention_blank_columns(tmp_path):
    old = """
        BeginDate,EndDate,Issuer,Country,Conviction,Sector
        ,,JBL,USA,,
    """
    new = """
        BeginDate,EndDate,Issuer,Country,Conviction,Sector
        ,,JBL,USA,,
        20240301,,IBM,,Low,
    """
    out = render(diff_text(tmp_path, old, new))
    added = out[out.index("IBM"):]
    assert "Conviction" in added
    assert "Sector" not in added


def test_long_sections_truncate(tmp_path):
    old = "BeginDate,EndDate,Issuer,Country\n"
    new = old + "".join(f",,K{i:03d},USA\n" for i in range(50))
    from conftest import load_patch, write_raw, diff_patches
    diff = diff_patches(
        load_patch(write_raw(tmp_path, "old.csv", old)),
        load_patch(write_raw(tmp_path, "new.csv", new)),
    )
    out = render(diff)
    assert re.search(r"and \d+ more", out)
    assert "50" in out, "the summary still reports the true total"


def test_added_column_usage_truncates_after_twenty_rows(tmp_path):
    old = (
        "BeginDate,EndDate,Issuer,Country\n"
        + "".join(f",,K{i:03d},USA\n" for i in range(50))
    )
    new = (
        "BeginDate,EndDate,Issuer,Country,Analyst\n"
        + "".join(f",,K{i:03d},USA,A{i:03d}\n" for i in range(50))
    )
    out = render(diff_text(tmp_path, old, new))

    assert out.count("Sets Analyst to") == 20
    assert "Sets Analyst to A019" in out
    assert "Sets Analyst to A020" not in out
    assert "... and 30 more" in out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _run(*args):
    return subprocess.run(
        [sys.executable, "-m", "patchdiff", *args],
        capture_output=True, text=True,
    )


def test_exit_zero_when_no_differences():
    r = _run(str(FIXTURES / "Patch0.csv"), str(FIXTURES / "Patch0.csv"))
    assert r.returncode == 0


def test_exit_one_when_differences_found():
    r = _run(str(FIXTURES / "Patch0.csv"), str(FIXTURES / "Patch1.csv"))
    assert r.returncode == 1


def test_exit_two_on_error(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("BeginDate,EndDate,Ticker,Country\n,,JBL,USA\n")
    r = _run(str(FIXTURES / "Patch0.csv"), str(bad))
    assert r.returncode == 2
    assert r.stderr.strip()


def test_exit_two_on_missing_file(tmp_path):
    r = _run(str(FIXTURES / "Patch0.csv"), str(tmp_path / "nope.csv"))
    assert r.returncode == 2
