"""Computing the diff.

Produces a PatchDiff and never formats a string; rendering lives in render.py.
That split is what makes a second output format cheap.

Columns are compared as sets, and a column present on only one side is excluded
from row comparison entirely. Rows are grouped by key alone, then matched within
each group in four stages of decreasing confidence. Full rules: docs/DIFF_SPEC.md.
"""

from .model import FieldChange, PatchDiff, PatchError, RowModification, sort_key


def diff_patches(old, new) -> PatchDiff:
    if old.key_column != new.key_column:
        raise PatchError(
            f"key column changed: {old.key_column!r} -> {new.key_column!r}. "
            f"The key column is the first column that is not BeginDate or "
            f"EndDate, so reordering columns can cause this."
        )

    old_cols, new_cols = set(old.value_columns), set(new.value_columns)
    shared = tuple(c for c in new.value_columns if c in old_cols)

    unchanged, modified, removed, added = [], [], [], []
    old_groups, new_groups = old.group_by_key(), new.group_by_key()
    for key in old_groups.keys() | new_groups.keys():
        u, m, r, a = _match_group(
            old_groups.get(key, []), new_groups.get(key, []), shared
        )
        unchanged += u
        modified += m
        removed += r
        added += a

    added.sort(key=sort_key)
    removed.sort(key=sort_key)
    modified.sort(key=lambda m: sort_key(m.new_row))
    unchanged.sort(key=lambda pair: sort_key(pair[1]))

    return PatchDiff(
        old=old,
        new=new,
        columns_added=[c for c in new.value_columns if c not in old_cols],
        columns_removed=[c for c in old.value_columns if c not in new_cols],
        rows_added=added,
        rows_removed=removed,
        rows_modified=modified,
        rows_unchanged=unchanged,
    )


def _match_group(old_rows, new_rows, shared):
    """Pair rows sharing a key. Returns (unchanged, modified, removed, added).

    Four stages of decreasing confidence, each running on what the previous
    stages left unmatched:

      1. exact       -- same scope and same values
      2. same scope  -- kept its time window, so probably the same rule with
                        edited values
      3. same values -- kept its values, so probably the same rule with an
                        edited window
      4. anything    -- pair greedily on number of matching columns. No 
                        minimum threshold, so a 1-vs-1 group always pairs

    Scope is a stronger identity signal than raw field count, which is why
    stage 2 runs before stage 3.
    """
    old_left, new_left = list(old_rows), list(new_rows)

    exact = _pair(old_left, new_left, shared,
                  lambda a, b: a.scope == b.scope and _values_equal(a, b, shared))
    pairs = (
        _pair(old_left, new_left, shared, lambda a, b: a.scope == b.scope)
        + _pair(old_left, new_left, shared,
                lambda a, b: _values_equal(a, b, shared))
        + _pair(old_left, new_left, shared, lambda a, b: True)
    )
    modified = [
        RowModification(o, n, _field_changes(o, n, shared)) for o, n in pairs
    ]
    return exact, modified, old_left, new_left


def _pair(old_left, new_left, shared, eligible):
    """Greedily pair eligible rows, closest first. Mutates the two lists.

    Sorting on line numbers after distance is what makes ties deterministic;
    without it the pairing follows dict order and output varies run to run.
    """
    candidates = sorted(
        ((_distance(o, n, shared), o.line_number, n.line_number, o, n)
         for o in old_left for n in new_left if eligible(o, n)),
        key=lambda c: c[:3],
    )

    pairs, used = [], set()
    for _, _, _, o, n in candidates:
        if id(o) in used or id(n) in used:
            continue
        pairs.append((o, n))
        used |= {id(o), id(n)}

    # Identity, not equality: two duplicate rows are equal by value and must
    # still be consumed independently.
    old_left[:] = [r for r in old_left if id(r) not in used]
    new_left[:] = [r for r in new_left if id(r) not in used]
    return pairs


def _values_equal(a, b, shared) -> bool:
    return all(a.values[c] == b.values[c] for c in shared)


def _distance(a, b, shared) -> int:
    """Differing fields, counting each date as one field."""
    return (sum(a.values[c] != b.values[c] for c in shared)
            + (a.scope.begin != b.scope.begin)
            + (a.scope.end != b.scope.end))


def _field_changes(old_row, new_row, shared):
    """Differing shared columns, in the new patch's column order."""
    return [FieldChange(c, old_row.values[c], new_row.values[c])
            for c in shared if old_row.values[c] != new_row.values[c]]
