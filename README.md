# patchdiff

Generates a human-readable diff between two patch CSVs, describing how the
application of the patch changes.

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

# My Thought Process/Editorial:

I started with the idea of a standard git style line number based diff. Display a summary:
'''
- X columns added (columns A, B, ...)
- Y columns removed (columns C, ...)
- X rows added
- Y rows removed
- Z rows modified
'''

And then display a diff for each row added/removed/modified:
'''
- Added row: a/b/c... (line N)
- Removed row: a/b/c/... (line M)
- Modified row: .../d/.../e/... (line L)
'''

Then I thought about what happens if we reorder rows, ex. from rows A/B/C to B/A/C? then the diff would be: - row A (line 1), + row A (line 2). Seems clunky...

According to the instructions, the goal of this exercise is to "print out a human readable diff explaining how the application of the patch would change from the original patch to the new patch." "Application of the patch" sounds like the key phrase here; reordering rows would not change the application of the patch, therefore it should not produce a diff. Additionally, the instructions also state that reordering columns should not produce a diff. These lead me to my first main assumption: *reordering rows should not produce a diff.*

So then if rows aren't identified by line number, then they must be identified by key. This assumption is supported by the instructions explicitly stating how to determine a key column for a patch, and that if the key columns of 2 patches don't match, the diff should error out. So let's match rows by their key. Okay then what happens when there are multiple rows with the same key? Like what if there are 2 rows with key PIPR in patch 3 and 1 row with key PIPR in patch 4? Is this 2 deleted rows and 1 added row? Or 1 modified row and 1 deleted row? And if it's a modified row then how do we determine which of the 2 old rows matches the single new row? Do we match same key rows across patches by line number? Or some sort of similarity between values? 

This duplicate key matching rows problem was the most interesting part of the assignment. I went through multiple iterations of matching logic and eventually settled on this algorithm: 1. Pair off exact matches first (all values in both rows identical), then 2. Pair off rows with same begin/end date but maybe different value fields, then 3. Pair off rows with same value fields but different begin/end date, then 4. Pair off the rest. Within tiers, we pair rows greedily by number of differing fields, with ties broken on line number. Afterwards, any unpaired rows from the old patch are removals; unpaired rows from the new patch are adds. The exact logic is detailed later on in "How the diff is created" section, as well as in docs/DIFF_SPEC.md.

## LLM Use/Points of Disagreement

I utilized AI assistance in implementing this program and especially with writing the test suite. However I want to make it clear that I very much thought through and weighed the options on every detail of the design, implementation, and output format.

Specific decisions where I disagreed with the LLM's decisions and manually corrected:
- Rejected using (keyColumn, beginDate, endDate) as composite key in favor of single keyColumn and a set of rules to match rows across patches. I made this decision because I noticed in the sample patches there can be multiple rows with same key column and begin/end dates.
- In models.py, the LLM implementation originally set the Patch.rows and RowModification.field_changes field types as tuples instead of lists. I assume this was in order to make these dataclasses hashable. I decided to change them to lists because IMO this data just makes more sense in list form, and we never hash Patch or RowModification objects anyway.
- Also in models.py, the LLM implementation originally created separate dataclasses for RowAddition and RowRemoval. I removed them because they were just wrappers over PatchRow; there wasn't any point to them and they just bloated the code.
- The LLM implementation originally included a Warnings section at the bottom of the output diff, displaying a warning when two rows had the same key but overlapping begin/end dates. I removed this feature because 1. I felt it made too many assumptions about the underlying patch system, and 2. having 2 rows with the same date range makes sense to me if they have different Country or Analyst or whatever.
- Manually customized specific wording and formatting inside render.py to make the output more clear and human readable. 
- In the matching logic, the LLM implementation originally suggested a "threshold" value (originally half) where if more than this number of value fields differ between an old and a new row, then we would never count it as a modification and instead always count it as deleted row + added row. I decided against this because I felt it introduced unnecessary complexity, and any threshold value would have been arbitrary.

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

## Matching rows when keys are not unique

This is the tricky part of the problem. `Patch1` contains two `PIPR` rows with identical (blank) date ranges, so `(key, BeginDate, EndDate)` is not a unique identifier. `Patch3 -> Patch4` collapses two `PIPR` rows into one.

I group rows by **key alone** and match within each group in four stages of
decreasing confidence — exact, same time window, same values, then anything —
pairing greedily by number of differing fields, with ties broken on line number.
Unmatched old rows are removals; unmatched new rows are additions. The full
algorithm is in `docs/DIFF_SPEC.md` section 5.

Three key decisions:

**Not ordinal position within the group.** Pairing the first old `PIPR` with the
first new `PIPR` is simpler, but it reintroduces exactly the order-dependence I
had just argued was meaningless: swapping two rows would report two
modifications for an unchanged patch. Similarity-based matching keeps the
behaviour consistent with the framing.

**Time window is not part of row identity.** Grouping on `(key, begin, end)`
would report an edit to a row's end date as a deletion plus an unrelated
insertion, which is technically true and reads badly. Grouping on key alone lets
stage 3 recognise it as a scope change to an existing rule.

**No distance threshold.** I considered only calling something "modified" if
one field changed, or fewer than half. Both add a tuning knob for a case that
barely arises: the threshold only matters when a group has two or more unmatched
rows on *both* sides, which none of the sample data does. A 1-vs-1 group is
always a modification, however many fields changed, because "modified" and
"removed + added" carry identical information there and the former reads better.

## Columns

Column identity is set-based, so reordering produces no diff, as the assignment
requires.

A column present on only one side is reported **once**, in its own section, and
excluded from row comparison entirely. The column section lists which rows the column touches:

```
Column changes
  + Analyst
      Sets Analyst to Bob for FR — from 2024-02-01
```

Added/removed columns are excluded from row comparison so that we do not produce a row diff for every row in the patch when we add/remove a column.

---

# Assumptions and known limitations

**Assumptions**

- Row order does not affect how a patch applies. If the real system applies rows
  in order so later rows shadow earlier ones, the reordering rule above is
  wrong.
- Value comparison is whitespace-insensitive and case-**sensitive**. `bob` and
  `Bob` are different values as far as the system applying the patch is
  concerned.
- Dates are parsed from `YYYYMMDD`, `M/D/YYYY`, and `YYYY-MM-DD`, and always
  rendered as `YYYY-MM-DD`. Ambiguous day-first dates may be interpreted as
  month-first or rejected.
- `BeginDate`/`EndDate` are treated as inclusive on both ends, per the
  assignment's description of `EndDate`.

**Normalized, because two files describing the same patch must not differ**

- UTF-8 BOM. Without `utf-8-sig`, the first header becomes `\ufeffBeginDate`
  and two identical Excel-saved files report every column as removed and
  re-added — a wrong answer, not a missing edge case.
- Header and cell whitespace.
- Blank trailing lines, which `csv.reader` yields as `[]` and which nearly
  every CSV ends with.

**Rejected rather than repaired**

Blank column names, rows whose cell count does not match the header, and dates
outside the three accepted formats all raise an error naming the file and line.
Excel does emit unnamed trailing columns and ragged rows, and both could be
silently cleaned up, but guessing at malformed input hides real problems. An
error the user can act on is the better answer.

**Known limitations**

- **The positional key rule can error on identical content.** The key column is
  "the first column that is not BeginDate/EndDate", so reordering columns such
  that a different column lands in that position changes the detected key and
  raises an error, even though the assignment says reordering should not produce
  a diff. 
- **Missing `BeginDate`/`EndDate` columns are not validated.** Such a patch
  parses with every row unscoped rather than erroring.
- **Greedy pairing is not guaranteed symmetric.** In a group with several
  unmatched rows on both sides and distance ties, diffing A against B and B
  against A can pair rows differently. Optimal assignment would fix it; the
  case does not arise in the sample data and I judged the complexity not worth
  it. 
- **A merge of two rows into one reads as a modification plus a removal.** In
  `Patch3 -> Patch4` a user merged two `PIPR` rows; the tool reports the net
  effect accurately but does not name it as a merge, which would require
  guessing intent.
- **Two-digit years are rejected rather than interpreted.** `2/1/24` could be
  2024 or 1924, and the sample data gives no basis for choosing.
- **Rules with overlapping time windows are not flagged.** The sample data
  contains rows that apply to the same issuer over overlapping dates and set
  the same column to different values. Whether that is a conflict depends on
  semantics the assignment does not state — an issuer legitimately having two
  countries or two analysts is not a contradiction — so the tool reports the
  diff and leaves interpretation to the reader.


## Tests

```bash
pip install pytest
python -m pytest
```

99 tests. `tests/test_sample_patches.py` asserts end-to-end expectations for
the provided sample progression; the other modules cover parsing, validation,
columns, matching, field classification and rendering.