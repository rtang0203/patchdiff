"""Computing the diff.

This module produces a PatchDiff and never formats a string. Rendering lives in
render.py. The split is what makes a second output format cheap.

The whole algorithm is DIFF_SPEC sections 3-6; the short version:

  columns are compared as sets, and columns present on only one side are
  excluded from row comparison entirely

  rows are grouped by key alone, then matched within each group in four
  stages of decreasing confidence, and whatever fails to match is an
  addition or a removal
"""

from itertools import combinations

from .model import (
    FieldChange,
    OverlapWarning,
    PatchDiff,
    PatchError,
    RowAddition,
    RowMatch,
    RowModification,
    RowRemoval,
)


def diff_patches(old, new) -> PatchDiff:
    if old.key_column != new.key_column:
        raise PatchError(
            f"key column changed: {old.key_column!r} -> {new.key_column!r}. "
            f"The key column is the first column that is not BeginDate or "
            f"EndDate, so reordering columns can cause this."
        )

    old_cols, new_cols = set(old.value_columns), set(new.value_columns)
    shared = tuple(c for c in new.value_columns if c in old_cols)
    columns_added = [c for c in new.value_columns if c not in old_cols]
    columns_removed = [c for c in old.value_columns if c not in new_cols]

    unchanged, modified, removed, added = [], [], [], []
    old_groups, new_groups = old.group_by_key(), new.group_by_key()

    for key in sorted(old_groups.keys() | new_groups.keys()):
        u, m, r, a = _match_group(
            old_groups.get(key, []), new_groups.get(key, []), shared
        )
        unchanged += u
        modified += m
        removed += [RowRemoval(row) for row in r]
        added += [RowAddition(row) for row in a]

    for bucket in (added, removed, modified, unchanged):
        bucket.sort(key=lambda entry: entry.sort_key)

    return PatchDiff(
        key_column=new.key_column,
        columns_added=columns_added,
        columns_removed=columns_removed,
        rows_added=added,
        rows_removed=removed,
        rows_modified=modified,
        rows_unchanged=unchanged,
        warnings=find_overlaps(new, new.value_columns),
        added_column_usage=_usage(new, columns_added),
        removed_column_usage=_usage(old, columns_removed),
    )


def _usage(patch, columns):
    """Rows where a one-sided column is populated, so the column section can
    say what the change actually does. A column blank in every row is a real
    header change with no effect on how the patch applies."""
    return {
        column: tuple(r for r in sorted(patch.rows, key=lambda r: r.sort_key)
                      if r.values.get(column))
        for column in columns
    }


# ---------------------------------------------------------------------------
# Matching within one key group
# ---------------------------------------------------------------------------

def _match_group(old_rows, new_rows, shared):
    """Pair rows sharing a key. Returns (unchanged, modified, removed, added).

    Four stages of decreasing confidence. Each runs on whatever the previous
    stages left unmatched:

      1. exact       — same scope and same values
      2. same scope  — the row kept its time window, so it is probably the
                       same rule with edited values
      3. same values — the row kept its values, so it is probably the same
                       rule with an edited window
      4. anything    — no threshold; a 1-vs-1 group always pairs, because
                       'modified' carries the same information as a
                       delete/insert pair and reads better

    Stage ordering is the judgment call. Scope is a stronger identity signal
    than raw field count, so a row that kept its window wins over a row that
    kept its values.
    """
    old_left, new_left = list(old_rows), list(new_rows)

    exact = _pair(old_left, new_left, shared,
                  lambda a, b: a.scope == b.scope and _values_equal(a, b, shared))
    same_scope = _pair(old_left, new_left, shared, lambda a, b: a.scope == b.scope)
    same_values = _pair(old_left, new_left, shared,
                        lambda a, b: _values_equal(a, b, shared))
    remainder = _pair(old_left, new_left, shared, lambda a, b: True)

    unchanged = [RowMatch(o, n) for o, n in exact]
    modified = [
        RowModification(o, n, _field_changes(o, n, shared))
        for o, n in same_scope + same_values + remainder
    ]
    return unchanged, modified, old_left, new_left


def _pair(old_left, new_left, shared, eligible):
    """Greedily pair eligible rows, closest first. Mutates the two lists.

    Sorting on line numbers after distance is what makes ties deterministic —
    without it the pairing depends on dict ordering and the output varies run
    to run.
    """
    candidates = sorted(
        (
            (_distance(o, n, shared), o.line_number, n.line_number, o, n)
            for o in old_left
            for n in new_left
            if eligible(o, n)
        ),
        key=lambda c: c[:3],
    )

    pairs, used_old, used_new = [], set(), set()
    for _, _, _, o, n in candidates:
        if id(o) in used_old or id(n) in used_new:
            continue
        pairs.append((o, n))
        used_old.add(id(o))
        used_new.add(id(n))

    # Identity, not equality: two duplicate rows can be equal by value and must
    # still be removed independently.
    old_left[:] = [r for r in old_left if id(r) not in used_old]
    new_left[:] = [r for r in new_left if id(r) not in used_new]
    return pairs


def _values_equal(a, b, shared) -> bool:
    return all(a.values[c] == b.values[c] for c in shared)


def _distance(a, b, shared) -> int:
    """Number of differing fields, counting each date as one field."""
    return (
        sum(a.values[c] != b.values[c] for c in shared)
        + (a.scope.begin != b.scope.begin)
        + (a.scope.end != b.scope.end)
    )


def _field_changes(old_row, new_row, shared):
    """Differing shared columns, in the new patch's column order."""
    return tuple(
        FieldChange(c, old_row.values[c], new_row.values[c])
        for c in shared
        if old_row.values[c] != new_row.values[c]
    )


# ---------------------------------------------------------------------------
# Overlap warnings
# ---------------------------------------------------------------------------

def find_overlaps(patch, columns):
    """Rows in one patch that share a key, overlap in time, and set the same
    column to different values.

    Overlap alone is not a conflict — the rows have to contend for the same
    column. Reported per key rather than per pair to keep the output short.
    """
    warnings = []
    for key, rows in sorted(patch.group_by_key().items()):
        contended, lines = set(), set()
        for a, b in combinations(rows, 2):
            if not a.scope.overlaps(b.scope):
                continue
            clash = {
                c for c in columns
                if a.values.get(c) and b.values.get(c)
                and a.values[c] != b.values[c]
            }
            if clash:
                contended |= clash
                lines |= {a.line_number, b.line_number}
        if contended:
            warnings.append(
                OverlapWarning(key, tuple(sorted(contended)), tuple(sorted(lines)))
            )
    return warnings
