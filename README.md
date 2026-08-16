# patchdiff

Generates a human-readable diff between two patch CSVs, describing how the
application of the patch changes.

## Requirements

Python 3.9+. No third-party dependencies. `pytest` is needed only for the tests.

## Running

```bash
python -m patchdiff tests/fixtures/Patch3.csv tests/fixtures/Patch4.csv
```

Exit codes follow `diff(1)` so the tool composes in a shell pipeline:
`0` no differences, `1` differences found, `2` error.

Example output:

```
Summary: 2 rows modified, 1 row removed, 3 unchanged

Modified rows
  ~ FR — from 2024-02-01  (line 5)
      Changes Analyst from Bob to Sally
  ~ PIPR — all time  (lines 6 -> 3)
      Now sets Sector to Consumer Discretionary (previously left unchanged)

Removed rows
  - PIPR — all time  (line 3)
      Was setting Sector to Consumer Discretionary
      Was setting Country to FRA

Warnings
  ! Issuer FR: rows at lines 4, 5 overlap in time and disagree on Country.
    Which value wins depends on the order the system applies rows in.
```

## Tests

```bash
pip install pytest
python -m pytest
```

101 tests. `tests/test_sample_patches.py` asserts end-to-end expectations for
every pair of the provided sample patches; the other modules cover parsing,
validation, columns, matching, field classification and rendering.

## Layout

| File | Responsibility |
| --- | --- |
| `patchdiff/model.py` | `Scope`, `PatchRow`, `Patch`, and the diff result types |
| `patchdiff/parser.py` | CSV reading, normalization, validation |
| `patchdiff/differ.py` | Column comparison, row matching, overlap detection |
| `patchdiff/render.py` | Formatting a `PatchDiff` as text |
| `patchdiff/cli.py` | Argument parsing and exit codes |
| `DIFF_SPEC.md` | Precise statement of every rule the diff follows |

The differ never formats a string and the renderer never computes a difference.
Adding a machine-readable output format means writing a second renderer against
the same `PatchDiff`; nothing in the diff logic would change.

---

# How I settled on this strategy

## A patch is a set of rules, not a spreadsheet

The obvious approach is a line-oriented `diff` over the CSV. I rejected it,
because the assignment asks for a diff of *how the patch applies*, and how a
patch applies has nothing to do with the order or position of its rows. A patch
row means "for this key, during this time window, set these columns". That is a
rule. A patch is a set of them.

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
Changes Analyst from Bob to Mike            value -> different value
Now sets Sector to Real Estate ...          blank -> value
No longer changes Country (previously ...)  value -> blank
```

The third is usually the most consequential edit a reviewer can miss.

## Matching rows when keys are not unique

This was the hard part, and the sample data is built to force it. `Patch1`
contains two `PIPR` rows with identical (blank) date ranges, so `(key,
BeginDate, EndDate)` is not a unique identifier. `Patch3 -> Patch4` collapses
two `PIPR` rows into one.

I group rows by **key alone** and match within each group in four stages of
decreasing confidence — exact, same time window, same values, then anything —
pairing greedily by number of differing fields, with ties broken on line number.
Unmatched old rows are removals; unmatched new rows are additions. The full
algorithm is in `DIFF_SPEC.md` section 5.

Three decisions inside that are worth calling out:

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
excluded from row comparison entirely. This matters more than it looks: without
it, adding a column marks every row in the file as modified and buries the
actual changes. The column section lists which rows the column touches, so the
consequence is visible without the noise:

```
Column changes
  + Analyst
      Sets Analyst to Bob for FR — from 2024-02-01
```

A column that is blank in every row is still a header change but has no effect
on how the patch applies, and says so.

## Conflict warnings

The sample patches contain rules that contradict each other. In `Patch1`, two
`PIPR` rows both apply for all time and both set `Country`, to `FRA` and `USA`.
`FR` has an all-time row and a from-2024-02-01 row that also disagree on
`Country`.

Which value wins depends on a precedence rule the assignment never specifies, so
the tool detects the overlap and surfaces it as a warning rather than resolving
it. Overlap alone is not flagged — the rows have to contend for the same column.

## Approach I considered and rejected

The semantically exact diff would ignore rows entirely: split each key's
timeline at every date boundary, compute the effective column values in each
segment on both sides, and diff the segments. It makes duplicate keys a
non-problem, since overlapping rules collapse into one effective state.

I did not do this for two reasons. It requires inventing the precedence rule
above. And its output is expressed in time segments that do not correspond to
anything the user edited, so a reviewer could not map a reported change back to
the row they need to fix. Row-level matching keeps the diff traceable to the
file, which matters more for a diff that exists to be reviewed.

---

# Assumptions and known limitations

**Assumptions**

- Row order does not affect how a patch applies. If the real system applies rows
  in order so later rows shadow earlier ones, the reordering rule above is
  wrong and the overlap warnings become errors.
- Value comparison is whitespace-insensitive and case-**sensitive**. `bob` and
  `Bob` are different values as far as the system applying the patch is
  concerned.
- Dates are parsed from `YYYYMMDD`, `M/D/YYYY`, `YYYY-MM-DD` and `M/D/YY`, and
  always rendered as `YYYY-MM-DD`. Ambiguous formats are not detected — a file
  written with day-first dates would parse incorrectly rather than fail.
- `BeginDate`/`EndDate` are treated as inclusive on both ends, per the
  assignment's description of `EndDate`.

**Edge cases handled deliberately, since Excel produces all of them**

- UTF-8 BOM. Without `utf-8-sig`, the first header becomes `\ufeffBeginDate`
  and two identical files report every column as removed and re-added.
- Header and cell whitespace.
- Blank trailing lines, which `csv.reader` yields as `[]` and which would
  otherwise trip the blank-key check on a valid file.
- Unnamed trailing columns, which would otherwise trip the duplicate-name check.

**Known limitations**

- **The positional key rule can error on identical content.** The key column is
  "the first column that is not BeginDate/EndDate", so reordering columns such
  that a different column lands in that position changes the detected key and
  raises an error, even though the assignment says reordering should not produce
  a diff. The two requirements are in tension; I implemented the positional rule
  as specified and made the error message explain the cause. Worth confirming
  which behaviour is wanted.
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
- Rows longer than the header have their extra cells dropped; there is no
  column for those values to belong to.
