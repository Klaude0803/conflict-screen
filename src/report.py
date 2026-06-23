"""Write a color-coded XLSX report using openpyxl.

Color coding by conflict status:
  - red   : CONFLICT
  - green : CLEAR
  - amber : UNVERIFIED

The header row is frozen so it stays visible while scrolling.
"""

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src import conflict as conflict_mod

# Fill colors per status (solid).
_FILLS = {
    conflict_mod.CONFLICT: PatternFill("solid", fgColor="F8CBAD"),   # red-ish
    conflict_mod.CLEAR: PatternFill("solid", fgColor="C6EFCE"),      # green
    conflict_mod.UNVERIFIED: PatternFill("solid", fgColor="FFEB9C"), # amber
}

_HEADERS = [
    "Handle",
    "Name",
    "Platform",
    "Subscribers",
    "Verified",
    "Status",
    "Category",
    "Tier-1 %",
    "Leverage",
    "Conflict Reason",
    "Negotiation Notes",
    "Source",
]


def write_report(results, out_path):
    """Write screened results to an XLSX file at out_path."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Conflict Screen"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="404040")
    for col, title in enumerate(_HEADERS, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")

    for r in results:
        bullets = "\n".join("• " + b for b in r.get("bullets", []))
        subs = r.get("subscribers")
        tier = r.get("tier_one_pct")
        row = [
            r.get("handle"),
            r.get("name") or "",
            r.get("platform") or "",
            subs if subs is not None else "",
            "yes" if r.get("verified") else "no",
            r.get("status"),
            r.get("category") or "",
            f"{tier:.0f}%" if tier is not None else "",
            r.get("leverage"),
            r.get("conflict_reason") or "",
            bullets,
            r.get("source") or "",
        ]
        ws.append(row)

        # Color the whole row by status.
        fill = _FILLS.get(r.get("status"))
        if fill:
            row_idx = ws.max_row
            for col in range(1, len(_HEADERS) + 1):
                ws.cell(row=row_idx, column=col).fill = fill
        # Wrap the notes column.
        ws.cell(row=ws.max_row, column=11).alignment = Alignment(
            wrap_text=True, vertical="top"
        )

    # Freeze the header row.
    ws.freeze_panes = "A2"

    # Reasonable column widths.
    widths = [18, 22, 12, 13, 9, 12, 16, 9, 11, 40, 50, 28]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    wb.save(out_path)
    return out_path
