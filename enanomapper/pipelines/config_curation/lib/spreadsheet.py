"""Dump sheet names, header rows, and a sample of data rows from an Excel
file, so a repair/authoring session can see the target layout without
opening the file itself.

Read-only (openpyxl in data_only/read-only mode) -- never writes back to the
Excel file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import openpyxl


def _cell_str(value) -> str:
    if value is None:
        return ""
    return str(value)


@dataclass
class SheetPreview:
    name: str
    index: int          # 1-based, matching driver-properties '#N' syntax
    n_rows: int
    n_cols: int
    header_rows: list[list[str]]   # first up to `header_rows` rows, in full
    sample_rows: list[list[str]]   # next up to `sample_rows` rows, in full


@dataclass
class SpreadsheetPreview:
    path: Path
    sheet_names: list[str]
    sheets: list[SheetPreview]


def read_spreadsheet(
    path: Path,
    sheet: int | str | None = None,
    *,
    header_rows: int = 3,
    sample_rows: int = 5,
    max_cols: int = 60,
) -> SpreadsheetPreview:
    """Preview one Excel file.

    `sheet` selects a single worksheet to preview in full: a 1-based index
    (matching the `#N` suffix convention in driver .properties lines) or a
    sheet name. If None, every sheet is previewed (cheap -- only the first
    `header_rows + sample_rows` rows of each are read).
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet_names = wb.sheetnames

        if sheet is None:
            targets = list(enumerate(sheet_names, start=1))
        elif isinstance(sheet, int):
            targets = [(sheet, sheet_names[sheet - 1])]
        else:
            targets = [(sheet_names.index(sheet) + 1, sheet)]

        previews = []
        for idx, name in targets:
            ws = wb[name]
            n_rows = ws.max_row or 0
            n_cols = ws.max_column or 0

            rows_wanted = header_rows + sample_rows
            row_iter = ws.iter_rows(
                max_row=rows_wanted, max_col=min(n_cols, max_cols)
            )
            collected: list[list[str]] = []
            for i, row in enumerate(row_iter, start=1):
                collected.append([_cell_str(c.value) for c in row])
                if i >= rows_wanted:
                    break

            sample_end = header_rows + sample_rows
            previews.append(
                SheetPreview(
                    name=name,
                    index=idx,
                    n_rows=n_rows,
                    n_cols=n_cols,
                    header_rows=collected[:header_rows],
                    sample_rows=collected[header_rows:sample_end],
                )
            )

        return SpreadsheetPreview(
            path=path, sheet_names=sheet_names, sheets=previews
        )
    finally:
        wb.close()
