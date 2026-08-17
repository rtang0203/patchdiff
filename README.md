# patchdiff

Generates a human-readable diff between two patch CSVs, describing how the
application of the patch changes.

The central model is:

**A patch row is a rule: for key K, during time scope S, set fields V.**

 Therefore it compares patch semantics rather than CSV text:

 - Row and column reordering are ignored.
 - Blank value cells mean “leave the existing system value unchanged,” not “set it to
  empty.”
 - Added or removed columns are reported once rather than as changes to every row.
 - Date-scope edits are treated as modifications to a rule where possible.
 - Duplicate keys are supported through similarity-based row matching. 

## Requirements

Python 3.9+. No third-party dependencies. `pytest` is needed only for the tests.

## Running

```bash
python -m patchdiff tests/fixtures/Patch3.csv tests/fixtures/Patch4.csv
```
Exit codes match the convention used by `diff` and `grep`, so scripts can
branch on the result without parsing output:
`0` no differences, `1` differences found, `2` error.

Example output:

```
Summary: 2 rows modified, 1 row removed, 3 unchanged

Modified rows
  ~ FR — from 2024-02-01  (line 5)
      Changes Analyst from Bob to Sally
  ~ PIPR — all time  (lines 6 -> 3)
      Now sets Sector to Consumer Discretionary (previously not set)

Removed rows
  - PIPR — all time  (line 3)
      Was setting Sector to Consumer Discretionary
      Was setting Country to FRA
```

### My Thought Process/Editorial:

I started with the idea of a standard git style line number based diff. Display a summary:
```
- X columns added (columns A, B, ...)
- Y columns removed (columns C, ...)
- X rows added
- Y rows removed
- Z rows modified
```

And then display a diff for each row added/removed/modified:
```
- Added row: a/b/c... (line N)
- Removed row: a/b/c/... (line M)
- Modified row: .../d/.../e/... (line L)
```

Then I thought about what happens if we reorder rows, ex. from rows A/B/C to B/A/C? then the diff would be: - row A (line 1), + row A (line 2). Seems clunky...

According to the instructions, the goal of this exercise is to "print out a human readable diff explaining how the application of the patch would change from the original patch to the new patch." "Application of the patch" sounds like the key phrase here; reordering rows would not change the application of the patch, therefore it should not produce a diff. Additionally, the instructions also state that reordering columns should not produce a diff. These lead me to my first main assumption: **reordering rows should not produce a diff.**

So if rows aren't identified by line number, then they must be identified by key. This assumption is supported by the instructions explicitly stating how to determine a key column for a patch, and that if the key columns of 2 patches don't match, the diff should error out. So let's match rows by their key. Okay, then what happens when there are multiple rows with the same key? Like what if there are 2 rows with key PIPR in patch 3 and 1 row with key PIPR in patch 4? Is this 2 deleted rows and 1 added row? Or 1 modified row and 1 deleted row? And if it's a modified row then how do we determine which of the 2 old rows matches the single new row? Do we match same key rows across patches by line number? Or some sort of similarity between values? 

This duplicate key matching rows problem was the most interesting part of the assignment. I went through multiple iterations of matching logic and eventually settled on this algorithm: 1. Pair off exact matches first (all values in both rows identical), then 2. Pair off rows with same begin/end date but maybe different value fields, then 3. Pair off rows with same value fields but different begin/end date, then 4. Pair off the rest. Within tiers, we pair rows greedily by number of differing fields, with ties broken on line number. Afterwards, any unpaired rows from the old patch are removals; unpaired rows from the new patch are adds. The exact logic is detailed in docs/DIFF_SPEC.md.

# How the diff is created

## A patch is a set of rules, not a spreadsheet

As explained above, I decided not to go with a line-oriented diff over the CSV, because the assignment asks for a diff of *how the patch applies*, and how a patch applies has nothing to do with the order of its rows. 

Everything below follows from that framing.

**Row reordering produces no diff.** Moving a row changes no rule, so there is
nothing to report. A line-oriented diff would report two changes for a
zero-change edit.

**Rows are identified by key, not by line.** The output names rows the way the
assignment's own example does — "for Issuer MSFT, the Analyst was changed from
Bob to Mike" — rather than by line number. Line numbers still appear, because
they help a user find the row they need to fix, but they identify a location in
a file, not a rule.

**Blank is not empty.** A blank value column means "leave the existing value in
the system alone". So clearing a cell is not a value change to the empty string,
it is the patch ceasing to touch that field, and it renders differently:

```
Changes Analyst from Bob to Mike                    value -> different value
Now sets Sector to Real Estate (previously not set) blank -> value
No longer sets Country (previously set to USA)      value -> blank
```

The third is usually the most consequential edit a reviewer can miss.

## Columns

Column identity is set-based, so reordering produces no diff, as the assignment
requires.

A column present on only one side is reported in its own section and excluded
from row matching and field-level modifications. The column section lists which
rows the column touches:

```
Column changes
  + Analyst
      Sets Analyst to Bob for FR — from 2024-02-01
```

Added/removed rows still list all of their populated values, including values
in added/removed columns, so each row description remains self-contained.

---

# Assumptions and known limitations

**Assumptions**

- Row order does not affect how a patch applies. If the real system applies rows
  in order so later rows shadow earlier ones, the reordering rule above is
  wrong.
- Value comparison preserves whitespace and is case-sensitive. `bob`, `Bob`,
  and ` Bob ` are different values as far as the system applying the patch is
  concerned.
- Dates are parsed from `YYYYMMDD`, `M/D/YYYY`, and `YYYY-MM-DD`, and always
  rendered as `YYYY-MM-DD`. Ambiguous day-first dates may be interpreted as
  month-first or rejected.
- `BeginDate`/`EndDate` are treated as inclusive on both ends, per the
  assignment's description of `EndDate`.

**Normalized, because these files still describe the same patch**

- UTF-8 BOM. Without `utf-8-sig`, the first header becomes `\ufeffBeginDate`
  and two identical Excel-saved files report every column as removed and
  re-added — a wrong answer, not a missing edge case.
- Physical blank lines, which `csv.reader` yields as `[]` and which do not
  contain a patch row.

**Rejected rather than repaired**

Cell contents are preserved exactly. Header names with surrounding whitespace,
missing required columns, blank or duplicate column names, malformed CSV/UTF-8,
rows whose cell count does not match the header, and dates outside the three
accepted formats all raise an actionable error. Guessing at malformed input
would hide data problems.

**Known limitations**

- **Key identification is positional.** I interpret the assignment's two rules
  together: the key is the first non-`BeginDate`/non-`EndDate` column, and the
  adjusted key must be the same as the original. Date and value columns may move
  without a diff as long as the same key remains the first non-date column;
  promoting a different value column to that position is a key change and
  raises an error.
- **Greedy pairing is not globally optimal or guaranteed symmetric.** In a
  many-to-many group, an optimal assignment could sometimes report fewer total
  field changes. I kept the staged greedy matcher because it is small,
  explainable, deterministic for a given input, and handles the supplied data.
  A globally optimal matcher would add substantial complexity for ambiguous
  rows that have no intrinsic identity in the file format.
- **A merge of two rows into one reads as a modification plus a removal.** In
  `Patch3 -> Patch4` a user merged two `PIPR` rows; the tool reports the net
  effect accurately but does not name it as a merge, which would require
  guessing intent.
- **Two-digit years are rejected rather than interpreted.** `2/1/24` could be
  2024 or 1924, and the sample data gives no basis for choosing.

## Layout

| File | Responsibility |
| --- | --- |
| `patchdiff/model.py` | `Scope`, `PatchRow`, `Patch`, and the diff result types |
| `patchdiff/parser.py` | CSV reading, normalization, validation |
| `patchdiff/differ.py` | Column comparison and row matching |
| `patchdiff/render.py` | Formatting a `PatchDiff` as text |
| `patchdiff/cli.py` | Argument parsing and exit codes |
| `docs/DIFF_SPEC.md` | Precise statement of every rule the diff follows |

The file arrangement is designed for modularity. differ.py produces a PatchDiff object, which could easily be rendered into a JSON/YAML/other machine readable format by a different renderer.

---

## Tests

```bash
pip install pytest
python -m pytest
```

`tests/test_sample_patches.py` asserts end-to-end expectations for the provided
sample progression; the other modules cover parsing, validation, columns,
matching, field classification and rendering.

#### LLM Use Disclaimer/Points of Disagreement

I utilized AI assistance in implementing this program and especially with writing the test suite.  I reviewed every resulting change and treated suggestions as proposals rather than requirements. Some examples of decisions where I rejected or simplified the proposed design based on the assignment and supplied data:

- Rejected using (keyColumn, beginDate, endDate) as composite key in favor of single keyColumn and a set of rules to match rows across patches. I made this decision because I noticed in the sample patches there can be multiple rows with same key column and begin/end dates.
- The LLM implementation originally included a Warnings section at the bottom of the output diff, displaying a warning when two rows had the same key but overlapping begin/end dates. I removed this feature because 1. I felt it made too many assumptions about the underlying patch system, and 2. having 2 rows with the same date range makes sense to me if they have different Country or Analyst or whatever.
- In the matching logic, the LLM implementation originally suggested a "threshold" value (originally half) where if more than this number of value fields differ between an old and a new row, then we would never count it as a modification and instead always count it as deleted row + added row. I decided against this because I felt it introduced unnecessary complexity, and any threshold value would have been arbitrary.
- In models.py, I changed Patch.rows and RowModification.field_changes types from tuples to lists. These collections are ordered results that are never hashed, so tuple immutability did not provide a useful invariant. 
- Also in models.py, removed separate dataclasses for RowAddition and RowRemoval. I felt they were unnecessary and bloated the code since they were basically just wrapper classes over PatchRow.