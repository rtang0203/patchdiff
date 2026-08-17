"""Formatting a PatchDiff as text. Computes nothing.

The diff is written in the language of the patch, not of the file: rows are
identified by key and time window, and a blank value column reads as "leaves
this alone" rather than as an empty string, because that is what it means.
"""

from .model import sort_key

MAX_ENTRIES = 20


def render(diff) -> str:
    if not diff.has_differences:
        return "No differences.\n"

    blocks = [_summary(diff), _columns(diff), _modified(diff)]
    for rows, title, marker, verb in (
        (diff.rows_added, "Added rows", "+", "Sets"),
        (diff.rows_removed, "Removed rows", "-", "Was setting"),
    ):
        blocks.append(_rows(rows, title, marker, verb))
    return "\n\n".join(b for b in blocks if b) + "\n"


def _summary(diff) -> str:
    counts = [
        (len(diff.columns_added), "column", "added"),
        (len(diff.columns_removed), "column", "removed"),
        (len(diff.rows_modified), "row", "modified"),
        (len(diff.rows_added), "row", "added"),
        (len(diff.rows_removed), "row", "removed"),
    ]
    parts = [f"{n} {noun if n == 1 else noun + 's'} {verb}"
             for n, noun, verb in counts if n]
    if diff.rows_unchanged:
        parts.append(f"{len(diff.rows_unchanged)} unchanged")
    return "Summary: " + ", ".join(parts)


def _columns(diff) -> str:
    """A column change is reported once here, never as a per-row change: a
    column added across 200 rows is one change, not 200."""
    if not (diff.columns_added or diff.columns_removed):
        return ""
    lines = ["Column changes"]
    for column in diff.columns_added:
        lines += [f"  + {column}"] + _usage(diff.new, column, "Sets")
    for column in diff.columns_removed:
        lines += [f"  - {column}"] + _usage(diff.old, column, "No longer sets")
    return "\n".join(lines)


def _usage(patch, column, verb) -> list:
    rows = [r for r in sorted(patch.rows, key=sort_key) if r.values.get(column)]
    if not rows:
        return ["      Blank in every row, so this does not change how the "
                "patch applies"]
    return [f"      {verb} {column} to {r.values[column]} for {_label(r)}"
            for r in rows[:MAX_ENTRIES]] + _more(len(rows))


def _modified(diff) -> str:
    if not diff.rows_modified:
        return ""
    lines = ["Modified rows"]
    for mod in diff.rows_modified[:MAX_ENTRIES]:
        header = f"  ~ {_label(mod.new_row)}"
        if mod.scope_changed:
            header += f", was {mod.old_row.scope.describe()}"
        lines.append(f"{header}  ({_lines(mod.old_row, mod.new_row)})")
        lines += [f"      {_change(c)}" for c in mod.field_changes]
    return "\n".join(lines + _more(len(diff.rows_modified)))


def _rows(rows, title, marker, verb) -> str:
    if not rows:
        return ""
    lines = [title]
    for row in rows[:MAX_ENTRIES]:
        lines.append(f"  {marker} {_label(row)}  (line {row.line_number})")
        # Only populated columns: a row that sets two fields and leaves five
        # blank is setting two things.
        lines += [f"      {verb} {c} to {v}" for c, v in row.populated.items()]
    return "\n".join(lines + _more(len(rows)))


def _change(change) -> str:
    if change.kind == "set":
        return (f"Now sets {change.column} to {change.new_value} "
                f"(previously not set)")
    if change.kind == "cleared":
        # The most consequential edit a reviewer can miss: the patch has
        # silently stopped touching a field.
        return (f"No longer sets {change.column} "
                f"(previously set to {change.old_value})")
    return (f"Changes {change.column} from {change.old_value} "
            f"to {change.new_value}")


def _label(row) -> str:
    return f"{row.key} \u2014 {row.scope.describe()}"


def _lines(old_row, new_row) -> str:
    a, b = old_row.line_number, new_row.line_number
    return f"line {a}" if a == b else f"line {a} -> {b}"


def _more(total) -> list:
    """The section truncates; the summary still reports the true total."""
    return [f"      ... and {total - MAX_ENTRIES} more"] if total > MAX_ENTRIES else []
