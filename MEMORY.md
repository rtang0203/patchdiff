# Project Memory

- 2026-08-16: Published as the private GitHub repository `rtang0203/patchdiff`; chose the README project name over the local folder name.
- 2026-08-16: Moved implementation modules into `patchdiff/` and tests plus sample fixtures into `tests/`; added explicit package API and module CLI entry points.
- 2026-08-16: Aligned tests with direct `PatchRow` addition/removal results and tuple-based unchanged pairs; removed obsolete warning coverage and redundant parser/determinism cases.
- 2026-08-16: Updated field-change documentation and tests to say “previously not set” and “no longer sets,” matching the clearer renderer terminology.
- 2026-08-16: Standardized mutable model collections on lists (`Patch.value_columns`, `Patch.rows`, and `RowModification.field_changes`); kept tuples only for fixed internal constants and unchanged row pairs.
- 2026-08-16: Removed redundant `PatchDiff.key_column` and corrected stale README date-format and specification-path documentation.
- 2026-08-16: Added rendering coverage proving populated added-column usage lists stop at 20 entries and report the remaining count.
