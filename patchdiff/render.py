"""Turning a PatchDiff into text a person can read.

This module never computes a difference; it only formats one.

The diff is written in the language of the patch rather than the language of
the file. Rows are identified by key and time window, not by position, and a
blank value column reads as "leaves this alone" rather than as an empty
string -- because that is what a blank value column means.
"""

MAX_ENTRIES = 20


def render(diff) -> str:
    if not diff.has_differences:
        return "No differences.\n"

    blocks = [_summary(diff)]
    blocks += [b for b in (
        _column_section(diff),
        _modified_section(diff),
        _added_section(diff),
        _removed_section(diff),
        _warning_section(diff),
    ) if b]
    return "\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _summary(diff) -> str:
    counts = [
        (len(diff.columns_added), "column", "added"),
        (len(diff.columns_removed), "column", "removed"),
        (len(diff.rows_modified), "row", "modified"),
        (len(diff.rows_added), "row", "added"),
        (len(diff.rows_removed), "row", "removed"),
    ]
    parts = [f"{n} {_plural(noun, n)} {verb}" for n, noun, verb in counts if n]
    if diff.rows_unchanged:
        parts.append(f"{len(diff.rows_unchanged)} unchanged")
    return "Summary: " + ", ".join(parts)


def _plural(noun, n):
    return noun if n == 1 else noun + "s"


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

def _column_section(diff) -> str:
    if not (diff.columns_added or diff.columns_removed):
        return ""

    lines = ["Column changes"]
    for column in diff.columns_added:
        lines.append(f"  + {column}")
        lines += _usage_lines(diff.added_column_usage.get(column, ()), column,
                              "Sets", "No rows populate it")
    for column in diff.columns_removed:
        lines.append(f"  - {column}")
        lines += _usage_lines(diff.removed_column_usage.get(column, ()), column,
                              "No longer sets", "No rows populated it")
    return "\n".join(lines)


def _usage_lines(rows, column, verb, empty_note):
    """A column change is reported once here, never as a per-row change -- a
    column added across 200 rows is one change, not 200."""
    if not rows:
        return [f"      {empty_note}, so this does not change how the patch applies"]
    shown = rows[:MAX_ENTRIES]
    lines = [f"      {verb} {column} to {r.values[column]} for {_row_label(r)}"
             for r in shown]
    if len(rows) > len(shown):
        lines.append(f"      ... and {len(rows) - len(shown)} more")
    return lines


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------

def _modified_section(diff) -> str:
    if not diff.rows_modified:
        return ""
    lines = ["Modified rows"]
    for mod in _truncate(diff.rows_modified, lines):
        header = f"  ~ {_row_label(mod.new_row)}"
        if mod.scope_changed:
            header += f", was {mod.old_row.scope.describe()}"
        header += f"  ({_line_ref(mod.old_row, mod.new_row)})"
        lines.append(header)
        lines += [f"      {_describe_change(c)}" for c in mod.field_changes]
    return "\n".join(lines)


def _added_section(diff) -> str:
    return _row_block(diff.rows_added, "Added rows", "+", "Sets")


def _removed_section(diff) -> str:
    return _row_block(diff.rows_removed, "Removed rows", "-", "Was setting")


def _row_block(entries, title, marker, verb) -> str:
    if not entries:
        return ""
    lines = [title]
    for entry in _truncate(entries, lines):
        row = entry.row
        lines.append(f"  {marker} {_row_label(row)}  ({_line_ref(row)})")
        # Only populated columns: a row that sets two fields and leaves five
        # blank is setting two things.
        for column, value in row.populated.items():
            lines.append(f"      {verb} {column} to {value}")
    return "\n".join(lines)


def _describe_change(change) -> str:
    if change.kind == "set":
        return (f"Now sets {change.column} to {change.new_value} "
                f"(previously left unchanged)")
    if change.kind == "cleared":
        # The most consequential edit a user can make: the patch has silently
        # stopped touching a field.
        return (f"No longer changes {change.column} "
                f"(previously set to {change.old_value})")
    return (f"Changes {change.column} from {change.old_value} "
            f"to {change.new_value}")


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------

def _warning_section(diff) -> str:
    if not diff.warnings:
        return ""
    lines = ["Warnings"]
    for w in diff.warnings:
        where = ", ".join(str(n) for n in w.line_numbers)
        cols = ", ".join(w.columns)
        lines.append(
            f"  ! {diff.key_column} {w.key}: rows at lines {where} overlap in "
            f"time and disagree on {cols}. Which value wins depends on the "
            f"order the system applies rows in."
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Shared bits
# ---------------------------------------------------------------------------

def _row_label(row) -> str:
    return f"{row.key} — {row.scope.describe()}"


def _line_ref(*rows) -> str:
    """Old line then new line, in that order -- direction is the useful part."""
    numbers = list(dict.fromkeys(r.line_number for r in rows))
    if len(numbers) == 1:
        return f"line {numbers[0]}"
    return "lines " + " -> ".join(str(n) for n in numbers)


def _truncate(entries, lines):
    """Show at most MAX_ENTRIES; the summary still reports the true total."""
    if len(entries) > MAX_ENTRIES:
        lines.append(f"  ... and {len(entries) - MAX_ENTRIES} more")
    return entries[:MAX_ENTRIES]
