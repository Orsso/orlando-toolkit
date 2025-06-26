from typing import Dict
from lxml import etree as ET
from docx.table import _Cell, Table  # type: ignore

from orlando_toolkit.core.utils import generate_dita_id
from orlando_toolkit.core.parser import iter_block_items
from docx.text.paragraph import Paragraph  # type: ignore
from orlando_toolkit.core.converter.helpers import process_paragraph_content_and_images

def create_dita_table(table: Table, image_map: Dict[str, str]) -> ET.Element:
    """Create a CALS DITA table from *table* handling complex merges (grid reconstruction)."""

    from docx.oxml.ns import qn as _qn
    from dataclasses import dataclass

    def _grid_span(tc):
        gs = tc.tcPr.find(_qn('w:gridSpan')) if tc.tcPr is not None else None
        return int(gs.get(_qn('w:val'))) if gs is not None else 1

    def _vmerge_type(tc):
        vm = tc.tcPr.find(_qn('w:vMerge')) if tc.tcPr is not None else None
        if vm is None:
            return None  # no vertical merge
        val = vm.get(_qn('w:val'))
        return 'restart' if val in ('restart', 'Restart') else 'continue'

    @dataclass
    class CellInfo:
        cell: _Cell  # python-docx cell object for content extraction
        rowspan: int = 1
        colspan: int = 1
        is_start: bool = True

    # ---------- build logical grid --------------------------------------
    grid: list[list[CellInfo | None]] = []
    vertical_tracker: dict[int, CellInfo] = {}
    max_cols = len(table.columns)
    # Track maximum width per column (in twips)
    col_widths = [0] * max_cols

    for r_idx, row in enumerate(table.rows):
        grid_row: list[CellInfo | None] = [None] * max_cols
        c_idx = 0
        phys_idx = 0  # index in row.cells (physical order)
        for tc in row._tr.tc_lst:
            while c_idx < max_cols and grid_row[c_idx] is not None:
                c_idx += 1
            if c_idx >= max_cols:
                break

            colspan = _grid_span(tc)
            # Capture cell width for the starting column only (Word stores per-cell)
            try:
                tcW = tc.tcPr.tcW  # type: ignore[attr-defined]
                if tcW is not None and tcW.type == 'dxa':  # width in twips
                    width_twips = int(tcW.w)
                    if width_twips > col_widths[c_idx]:
                        col_widths[c_idx] = width_twips
            except Exception:
                pass
            v_type = _vmerge_type(tc)

            if v_type == 'continue':
                if c_idx in vertical_tracker:
                    starter = vertical_tracker[c_idx]
                    starter.rowspan += 1
                for span_col in range(colspan):
                    if c_idx + span_col < max_cols:
                        grid_row[c_idx + span_col] = None
                c_idx += colspan
                phys_idx += colspan
                continue

            cell_info = CellInfo(cell=row.cells[phys_idx], colspan=colspan)
            if v_type == 'restart':
                vertical_tracker[c_idx] = cell_info
            else:
                vertical_tracker.pop(c_idx, None)

            for span_col in range(colspan):
                if c_idx + span_col < max_cols:
                    grid_row[c_idx + span_col] = cell_info if span_col == 0 else None
            c_idx += colspan
            phys_idx += 1

        for col_key in list(vertical_tracker.keys()):
            if grid_row[col_key] is not None:
                continue
        grid.append(grid_row)

    dita_table = ET.Element('table', id=generate_dita_id())
    tgroup = ET.SubElement(dita_table, 'tgroup', id=generate_dita_id(), cols=str(max_cols))

    # Create <colspec> with colwidth if available (convert twips→mm)
    for i in range(max_cols):
        col_attrs = {'colname': f'col{i+1}'}
        if col_widths[i]:
            mm = col_widths[i] / 1440 * 25.4
            col_attrs['colwidth'] = f"{mm:.1f}mm"
        ET.SubElement(tgroup, 'colspec', **col_attrs)

    # Only create <thead> when the source table has more than one row; otherwise
    # the first (and only) row belongs in <tbody>.  Creating an empty <thead>
    # violates the DITA DTD (must contain at least one <row>).
    use_header = len(grid) > 1

    thead = ET.SubElement(tgroup, 'thead', id=generate_dita_id()) if use_header else None
    tbody = ET.SubElement(tgroup, 'tbody', id=generate_dita_id())

    for r_idx, grid_row in enumerate(grid):
        row_parent = thead if (use_header and r_idx == 0 and thead is not None) else tbody
        row_el = ET.SubElement(row_parent, 'row', id=generate_dita_id())

        for c_idx, cell_info in enumerate(grid_row):
            if cell_info is None or not cell_info.is_start:
                continue

            attrs = {'id': generate_dita_id(), 'colsep': '1', 'rowsep': '1'}
            if cell_info.rowspan > 1:
                attrs['morerows'] = str(cell_info.rowspan - 1)
            if cell_info.colspan > 1:
                attrs['namest'] = f'col{c_idx+1}'
                attrs['nameend'] = f'col{c_idx+cell_info.colspan}'

            entry_el = ET.SubElement(row_el, 'entry', **attrs)

            for p in cell_info.cell.paragraphs:
                p_el = ET.SubElement(entry_el, 'p', id=generate_dita_id())
                # Reuse helper so images inside tables are preserved
                process_paragraph_content_and_images(p_el, p, image_map, None)

            # Detect vertical (rotated) text direction
            try:
                td = cell_info.cell._tc.tcPr.find('.//w:textDirection', namespaces={'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'})
                if td is not None and td.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val') in ('tbRl', 'btLr'):
                    entry_el.set('outputclass', (entry_el.get('outputclass', '') + ' rotate-90').strip())
            except Exception:
                pass

    return dita_table 