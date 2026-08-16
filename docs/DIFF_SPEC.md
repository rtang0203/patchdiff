# Patch Diff — Specification

How the diff between two patch CSVs is computed and rendered. This is the
reference for implementation and tests; the README covers *why* these choices
were made, this covers *what* they are.

---

## 0. Vocabulary

| Term | Meaning |
| --- | --- |
| **Well-known columns** | `BeginDate` and `EndDate`. Define the time window a row applies to. |
| **Key column** | The first column that is not `BeginDate` or `EndDate`, by position. |
| **Value columns** | Every remaining column. |
| **Scope** | The `(BeginDate, EndDate)` pair of a row. |
| **Rule** | One patch row: "for key K, during scope S, set these value columns". |
| **Shared value columns** | Value columns present in *both* patches. |

A patch is a **set of rules**, not a sequence. Row order carries no meaning and
is never reported as a difference.

---

## 1. Parsing and normalization

Applied to both files before anything is compared.

1. Read with `encoding="utf-8-sig"` so an Excel-written BOM does not corrupt the
   first header cell.
2. `strip()` every header name and every cell value.
3. Skip rows that are wholly empty (the `csv` module yields `[]` or all-blank
   lists for stray trailing newlines).
4. Drop trailing columns whose header is blank **and** whose value is blank in
   every data row. Excel exports sometimes carry these.
5. Record the original 1-based file line number on every row. This is metadata:
   it is used for output and for deterministic tie-breaking, and is **never**
   part of an equality comparison.
6. Parse dates. Accepted input formats, tried in order:
   `%Y%m%d`, `%m/%d/%Y`, `%Y-%m-%d`, `%m/%d/%y`.
   A blank date stays `None`. An unparseable non-blank date is an error.

Two files that differ only in BOM, whitespace, date format, row order, or
column order produce **no diff**.

---

## 2. Validation

Errors abort with a message and a non-zero exit code.

| Condition | Result |
| --- | --- |
| Duplicate column names (after strip) in either file | **Error** |
| Key column name differs between the two files | **Error** |
| A row has a blank key cell | **Error** |
| A non-blank date cell cannot be parsed | **Error** |
| Fewer than 3 columns (no room for dates + key) | **Error** |
| `BeginDate`/`EndDate` absent | Not validated — out of scope |

The key column is computed **positionally in each file independently**, then the
two names are compared. A consequence worth documenting for users: reordering
columns such that a *different* non-date column lands first will error even
though the content is unchanged. That falls out of the positional rule in the
assignment; it is accepted rather than worked around.

---

## 3. Column diff

Column order is not part of identity. Columns are compared as **sets** of names.

- `added` = value columns in new but not old
- `removed` = value columns in old but not new
- `shared` = the intersection

Rules:

1. Added and removed columns are reported **once**, in their own section — never
   as a per-row change. A column added across 200 rows is one change, not 200.
2. Added and removed columns are **excluded from all row-level comparison**.
   Only shared value columns participate in matching and field diffs.
3. For an added column, enumerate the rows where it is populated, with the value.
   For a removed column, enumerate where it *was* populated.
4. If the column is blank in every row, report the column change and state that
   it does not affect how the patch applies. No row list.
5. Lists truncate at 20 entries with `... and N more`.

---

## 4. Row grouping

Rows are grouped by **key value alone**. Scope is *not* part of row identity —
a row whose end date moved is an edit to that rule, not a delete plus an insert.

Matching happens independently within each key group. A group with `n` old rows
and `m` new rows produces some number of matched pairs; unmatched old rows are
**removals**, unmatched new rows are **additions**.

---

## 5. Matching algorithm

Within one key group, in order. Each stage runs on whatever is still unmatched.

**Stage 1 — Exact.**
Scope equal AND all shared value columns equal. Pair off; mark **unchanged**.
Duplicate identical rows are indistinguishable, so pair them in line order.

**Stage 2 — Same scope, different values.**
Candidates are pairs whose scopes are equal. Pair by the greedy procedure below.
Result: **modified** (value edit).

**Stage 3 — Same values, different scope.**
Candidates are pairs whose shared value columns are all equal. Pair greedily.
Result: **modified** (scope edit).

**Stage 4 — Everything else.**
Pair greedily with no eligibility restriction and no distance threshold. A
1-vs-1 group therefore always pairs, however different the two rows are: there
is nothing else either could match, and "modified" carries the same information
as a delete/insert pair while reading better. Result: **modified**.

Because there is no threshold, stage 4 needs no special case for 1-vs-1 — the
greedy pass handles it. All four stages are the same routine with a different
eligibility predicate.

**Stage 5.** Unmatched old → **removed**. Unmatched new → **added**.

### Greedy pairing procedure

1. Compute *distance* for every candidate pair: the number of differing fields,
   counting `BeginDate` and `EndDate` as one field each plus one per differing
   shared value column.
2. Sort candidate pairs by `(distance, old_line_number, new_line_number)`.
3. Walk the sorted list, accepting a pair if neither of its rows is already
   matched.

No distance threshold. A 1-vs-1 group is always a modification.

Sorting on line numbers is what makes ties deterministic; without it the output
varies run to run and golden tests go flaky.

---

## 6. Field-level changes within a modified row

Only shared value columns are examined. Unchanged fields are not reported.

| Old | New | Reported as |
| --- | --- | --- |
| blank | `V` | `Now sets {col} to {V} (previously left unchanged)` |
| `V` | blank | `No longer changes {col} (previously set to {V})` |
| `A` | `B` | `Changes {col} from {A} to {B}` |

The blank cases carry the domain meaning — a blank value column means "leave the
existing value in the system alone", so clearing a cell means the patch has
silently stopped touching that field. That is usually the most important thing
in a diff and must not render as `changed from Bob to ""`.

A scope change is rendered on the row header, not as a bullet:

```
FR — from 2024-02-01 (was: all time)
```

### Scope rendering

| BeginDate | EndDate | Rendered |
| --- | --- | --- |
| blank | blank | `all time` |
| `D` | blank | `from {D}` |
| blank | `D` | `through {D}` |
| `D1` | `D2` | `from {D1} through {D2}` |

Dates always render canonically as `YYYY-MM-DD`, never echoed back in the
input's format.

---

## 7. Added and removed rows

Only **populated** value columns are listed. A new row that sets two fields and
leaves five blank is setting two things.

```
+ IBM — from 2024-03-01 (line 6)
    Sets Conviction to Low

- PIPR — all time (line 3)
    Was setting Sector to Consumer Discretionary
    Was setting Country to FRA
```

---

## 8. Output structure and ordering

```
Summary
Column changes
Modified rows
Added rows
Removed rows
Warnings
```

Summary leads because users skim the first line to decide whether the change is
what they expected. Counts: columns added/removed, rows added/removed/modified,
rows unchanged.

Because row order is meaningless, output cannot be in file order. Every section
sorts by `(key, begin_date, end_date, line_number)` with `None` dates sorting
first. Deterministic and stable regardless of input ordering.

Sections with nothing in them are omitted. Long sections truncate at 20 with
`... and N more`.

---

## 9. Warnings (non-fatal)

Emitted after the diff, for the **new** patch only.

**Overlapping scopes.** Two rows sharing a key, whose date ranges overlap, that
both populate the same value column. The patch is self-conflicting and its
result depends on a precedence rule the assignment never specifies. Example from
the sample data:

```
FR: rows at lines 3 and 4 overlap from 2024-02-01 and both set Country
    (USA, FRA)
```

The conflict is surfaced, not resolved.

---

## 10. Exit codes

| Code | Meaning |
| --- | --- |
| `0` | No differences |
| `1` | Differences found |
| `2` | Error |

Mirrors `diff(1)`, so the tool composes in a shell pipeline.

---

## 11. Worked examples from the sample patches

**Patch0 → Patch1.** Two rows added, nothing else. Both new rows land in groups
that already had an exact match, so they fall to Stage 5 as additions.

**Patch1 → Patch2.** `Analyst` added, populated on one row. Since added columns
are excluded from row comparison, all five rows are unchanged. One column-level
entry, zero row entries.

**Patch2 → Patch3.** Columns reordered (`Sector` moves forward) and `IBM` added.
Set comparison means the reorder is invisible. One addition.

**Patch3 → Patch4.** The interesting one. `PIPR` has two old rows and one new
row, all with blank scope:

| | Sector | Country | Conviction |
| --- | --- | --- | --- |
| old A (line 3) | Consumer Discretionary | FRA | |
| old B (line 6) | | USA | High |
| new N (line 3) | Consumer Discretionary | USA | High |

Stage 1 finds no exact match. Stage 2 applies to both candidates since all
scopes are blank: `distance(A,N) = 2` (Country, Conviction), `distance(B,N) = 1`
(Sector). Greedy takes `(B,N)`; `A` falls through to Stage 5 as a removal.

Output: `PIPR` modified — now sets Sector to Consumer Discretionary — plus a
`PIPR` removal. A human might describe the same edit as "merged two rows into
one"; the diff describes the net effect instead, which is accurate and does not
require guessing intent. `FR` at 2024-02-01 changes Analyst from Bob to Sally.
