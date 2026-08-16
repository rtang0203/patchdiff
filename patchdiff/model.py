"""Data model for patches and diffs.

Two rules shape everything here:

1. ``PatchRow.values`` contains value columns and nothing else. Dates live in a
   ``Scope``, the key lives in ``key``, the line number is metadata. Comparison
   code therefore never has to remember to exclude anything.
2. Anything derivable is a property, so it cannot drift out of sync with the
   data it is derived from.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

WELL_KNOWN_COLUMNS = ("BeginDate", "EndDate")


class PatchError(Exception):
    """A patch file is malformed, or two patches cannot be compared."""


# ---------------------------------------------------------------------------
# Patch structure
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Scope:
    """The time window a patch row applies to. ``None`` means unbounded."""

    begin: Optional[date] = None
    end: Optional[date] = None

    def overlaps(self, other: "Scope") -> bool:
        """True if the two windows share at least one day. Both ends are
        inclusive, per the assignment's description of EndDate."""
        starts_before_other_ends = (
            self.begin is None or other.end is None or self.begin <= other.end
        )
        other_starts_before_self_ends = (
            other.begin is None or self.end is None or other.begin <= self.end
        )
        return starts_before_other_ends and other_starts_before_self_ends

    def describe(self) -> str:
        if self.begin is None and self.end is None:
            return "all time"
        if self.end is None:
            return f"from {self.begin.isoformat()}"
        if self.begin is None:
            return f"through {self.end.isoformat()}"
        return f"from {self.begin.isoformat()} through {self.end.isoformat()}"

    @property
    def sort_key(self):
        """Unscoped rows sort before dated ones; ``None`` is not orderable."""
        return (
            (0,) if self.begin is None else (1, self.begin),
            (0,) if self.end is None else (1, self.end),
        )


@dataclass
class PatchRow:
    """One rule: for ``key``, during ``scope``, set these value columns.

    ``line_number`` is excluded from equality — it is a file artifact, not part
    of what the row means.
    """

    key: str
    scope: Scope
    values: dict          # value columns only; blank cells are ""
    line_number: int = field(compare=False, default=0)

    @property
    def populated(self) -> dict:
        """Only the columns this row actually sets. A blank value column means
        'leave the existing value alone', so blanks are not part of the rule."""
        return {c: v for c, v in self.values.items() if v}

    @property
    def sort_key(self):
        return (self.key, self.scope.sort_key, self.line_number)


@dataclass
class Patch:
    key_column: str
    value_columns: tuple      # declaration order, kept for rendering
    rows: tuple

    def group_by_key(self) -> dict:
        """Rows bucketed by key value, each bucket in file order.

        Grouping is a matching concern, so it happens here on demand rather
        than in the parser — validation and rendering both want the flat list.
        """
        groups: dict = {}
        for row in self.rows:
            groups.setdefault(row.key, []).append(row)
        return groups


# ---------------------------------------------------------------------------
# Diff results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldChange:
    column: str
    old_value: str
    new_value: str

    @property
    def kind(self) -> str:
        if not self.old_value:
            return "set"        # the patch now touches a field it did not
        if not self.new_value:
            return "cleared"    # the patch has stopped touching a field
        return "changed"


@dataclass(frozen=True)
class RowMatch:
    """An unchanged row, paired across the two patches."""

    old_row: PatchRow
    new_row: PatchRow

    @property
    def sort_key(self):
        return self.new_row.sort_key


@dataclass(frozen=True)
class RowModification:
    old_row: PatchRow
    new_row: PatchRow
    field_changes: tuple

    @property
    def key(self) -> str:
        return self.new_row.key

    @property
    def scope_changed(self) -> bool:
        return self.old_row.scope != self.new_row.scope

    @property
    def sort_key(self):
        return self.new_row.sort_key


@dataclass(frozen=True)
class RowAddition:
    row: PatchRow

    @property
    def sort_key(self):
        return self.row.sort_key


@dataclass(frozen=True)
class RowRemoval:
    row: PatchRow

    @property
    def sort_key(self):
        return self.row.sort_key


@dataclass(frozen=True)
class OverlapWarning:
    """Two or more rows in one patch share a key, overlap in time, and set the
    same column to different values. The result depends on a precedence rule
    the assignment never specifies, so this is surfaced, not resolved."""

    key: str
    columns: tuple
    line_numbers: tuple


@dataclass
class PatchDiff:
    key_column: str
    columns_added: list
    columns_removed: list
    rows_added: list
    rows_removed: list
    rows_modified: list
    rows_unchanged: list
    warnings: list
    # Which rows a one-sided column actually touches, so the column section can
    # explain the consequence instead of just naming the column.
    added_column_usage: dict = field(default_factory=dict)
    removed_column_usage: dict = field(default_factory=dict)

    @property
    def has_differences(self) -> bool:
        return bool(
            self.columns_added
            or self.columns_removed
            or self.rows_added
            or self.rows_removed
            or self.rows_modified
        )
