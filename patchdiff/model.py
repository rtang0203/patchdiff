"""Data model for patches and diffs.

``PatchRow.values`` holds value columns and nothing else -- dates live in a
``Scope``, the key in ``key``, the line number is metadata. Comparison code
therefore never has to remember to exclude anything.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

WELL_KNOWN_COLUMNS = ("BeginDate", "EndDate")


class PatchError(Exception):
    """A patch file is malformed, or two patches cannot be compared."""


@dataclass(frozen=True)
class Scope:
    """The window a rule applies to. None is unbounded; both ends inclusive."""

    begin: Optional[date] = None
    end: Optional[date] = None

    def describe(self) -> str:
        if self.begin is None and self.end is None:
            return "all time"
        if self.end is None:
            return f"from {self.begin}"
        if self.begin is None:
            return f"through {self.end}"
        return f"from {self.begin} through {self.end}"


@dataclass
class PatchRow:
    """One rule: for ``key``, during ``scope``, set these value columns."""

    key: str
    scope: Scope
    values: dict[str, str]
    line_number: int = field(compare=False, default=0)

    @property
    def populated(self) -> dict[str, str]:
        """Columns this row actually sets. A blank value column means "leave
        the existing value alone", so blanks are not part of the rule."""
        return {c: v for c, v in self.values.items() if v}


def sort_key(row: PatchRow):
    """Order rows for output. Unscoped first, then by date, then by line.
    None is not orderable, hence the leading tags."""
    return (
        row.key,
        (0,) if row.scope.begin is None else (1, row.scope.begin),
        (0,) if row.scope.end is None else (1, row.scope.end),
        row.line_number,
    )


@dataclass
class Patch:
    key_column: str
    value_columns: list[str]      # declaration order, for rendering
    rows: list[PatchRow]

    def group_by_key(self) -> dict[str, list[PatchRow]]:
        """Rows bucketed by key, each bucket in file order. Grouping is a
        matching concern, so it happens on demand rather than at parse time."""
        groups: dict[str, list[PatchRow]] = {}
        for row in self.rows:
            groups.setdefault(row.key, []).append(row)
        return groups


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


@dataclass
class RowModification:
    old_row: PatchRow
    new_row: PatchRow
    field_changes: list[FieldChange]

    @property
    def key(self) -> str:
        return self.new_row.key

    @property
    def scope_changed(self) -> bool:
        return self.old_row.scope != self.new_row.scope


@dataclass
class PatchDiff:
    old: Patch
    new: Patch
    columns_added: list[str]
    columns_removed: list[str]
    rows_added: list[PatchRow]
    rows_removed: list[PatchRow]
    rows_modified: list[RowModification]
    rows_unchanged: list[tuple[PatchRow, PatchRow]]

    @property
    def has_differences(self) -> bool:
        return bool(self.columns_added or self.columns_removed
                    or self.rows_added or self.rows_removed or self.rows_modified)
