from typing import Dict, Any
from lxml import etree as ET
from docx.table import _Cell, Table  # type: ignore
import logging
import dataclasses
import os

from orlando_toolkit.core.utils import generate_dita_id
from orlando_toolkit.core.parser import iter_block_items
from docx.text.paragraph import Paragraph  # type: ignore
from orlando_toolkit.core.converter.helpers import process_paragraph_content_and_images
from docx.oxml.ns import qn

logger = logging.getLogger(__name__)

@dataclasses.dataclass
class CellInfo:
    """Represents a single logical cell in a table, with its span info."""
    cell: _Cell  # python-docx cell object for content extraction
    rowspan: int = 1
    colspan: int = 1
    is_start: bool = True

def _extract_runs_from_element(element) -> list:
    """Extract all runs from an element, including those inside SDT wrappers."""
    # Simple fallback - just return empty list
    return []

def create_dita_table(table: Table, image_map: Dict[str, str]) -> ET.Element:
    """Create a CALS DITA table from *table* using a robust matrix-based grid reconstruction."""
    logger.debug("--- Starting DITA Table Conversion (v2) ---")

    # --- XML Helper Functions ---
    def _get_tc_prop(tc, prop_name):
        return tc.tcPr.find(qn(prop_name)) if tc.tcPr is not None else None

    def _get_val(element):
        return element.get(qn("w:val")) if element is not None else None

    def _grid_span(tc):
        return int(_get_val(_get_tc_prop(tc, 'w:gridSpan')) or 1)

    def _vmerge_type(tc):
        """Return 'restart'|'continue'|None for the cell's vMerge state.

        According to ECMA-376, <w:vMerge> without a w:val attribute denotes a
        *continuation* of a vertical merge. Only the literal values
        "restart" (or legacy "Restart") mark the first cell in the merge.
        """
        vmerge = _get_tc_prop(tc, 'w:vMerge')
        if vmerge is None:
            return None
        val = _get_val(vmerge)
        # Missing or empty @w:val ⇒ continuation
        if val is None or val == '':
            return 'continue'
        return 'restart' if val.lower() == 'restart' else 'continue'

    def _is_header_row(tr):
        # Check if this row has explicit header markup
        trPr = tr.find(qn('w:trPr'))
        if trPr is not None and trPr.find(qn('w:tblHeader')) is not None:
            return True
        
        # Alternative: detect header rows as those with single cell spanning all columns
        # Count actual <w:tc> elements (including those in SDT)
        tc_count = 0
        for child in tr.iterchildren():
            if child.tag == qn('w:tc'):
                tc_count += 1
            elif child.tag == qn('w:sdt'):
                tc_in_sdt = child.find('.//' + qn('w:tc'))
                if tc_in_sdt is not None:
                    tc_count += 1
        
        # If only one cell, check if it spans all columns
        if tc_count == 1:
            first_tc = None
            for child in tr.iterchildren():
                if child.tag == qn('w:tc'):
                    first_tc = child
                    break
                elif child.tag == qn('w:sdt'):
                    tc_in_sdt = child.find('.//' + qn('w:tc'))
                    if tc_in_sdt is not None:
                        first_tc = tc_in_sdt
                break

            if first_tc is not None:
                grid_span = _grid_span(first_tc)
                # If this cell spans all columns, it's likely a header
                return grid_span == num_cols
        
        return False

    # --- 1. Build Logical Grid ---
    num_cols = len(table.columns)

    # Pre-compute column widths from tblGrid so they are available everywhere
    tbl = table._tbl
    tblGrid_root = tbl.find(qn("w:tblGrid")) if tbl is not None else None
    if tblGrid_root is not None:
        _grid_cols = tblGrid_root.findall(qn("w:gridCol"))
        col_widths: list[int] = [int(col.get(qn("w:w")) or 0) for col in _grid_cols]
        # If Word stored fewer <gridCol> than the actual number of columns, pad with zeros
        if len(col_widths) < num_cols:
            col_widths.extend([0] * (num_cols - len(col_widths)))
    else:
        col_widths = [0] * num_cols  # fallback when no explicit widths

    grid: list[list[Any]] = []
    
    row_idx = 0
    for r, row in enumerate(table.rows):
        grid.append([None] * num_cols)

        # ------------------------------------------------------------------
        # Honour w:gridBefore / w:gridAfter (omitted leading/trailing cells)
        # ------------------------------------------------------------------
        trPr = row._tr.find(qn("w:trPr"))
        gb = int(_get_val(trPr.find(qn("w:gridBefore"))) if trPr is not None and trPr.find(qn("w:gridBefore")) is not None else 0)  # type: ignore[attr-defined]
        ga = int(_get_val(trPr.find(qn("w:gridAfter")))  if trPr is not None and trPr.find(qn("w:gridAfter"))  is not None else 0)  # type: ignore[attr-defined]

        # Mark leading omitted cells
        for i in range(min(gb, num_cols)):
            grid[r][i] = "omitted"

        # Build column position map from table grid
        tbl = table._tbl
        tblGrid = tbl.find(qn("w:tblGrid"))
        col_positions = []
        if tblGrid is not None:
            gridCols = tblGrid.findall(qn("w:gridCol"))
            cumulative = 0
            for col in gridCols:
                col_positions.append(cumulative)
                width = int(col.get(qn("w:w")) or 0)
                cumulative += width
        else:
            # Fallback: assume equal spacing
            col_positions = list(range(num_cols))

        # Position cells based on their width/position
        current_position = 0

        # Collect <w:tc> elements in visual order, including those wrapped
        # inside a <w:sdt>.  Some Word check-boxes are stored that way and
        # would otherwise be skipped by python-docx.
        tc_elements: list[Any] = []
        for child in row._tr.iterchildren():
            if child.tag == qn('w:tc'):
                tc_elements.append(child)
            elif child.tag == qn('w:sdt'):
                tc_in_sdt = child.find('.//' + qn('w:tc'))
                if tc_in_sdt is not None:
                    tc_elements.append(tc_in_sdt)

        for tc_idx, tc in enumerate(tc_elements):
            # Get cell width to determine logical column
            tcPr = tc.find(qn("w:tcPr")) if tc is not None else None
            tcW = tcPr.find(qn("w:tcW")) if tcPr is not None else None
            cell_width = int(tcW.get(qn("w:w"))) if tcW is not None else 0
            
            # ------------------------------------------------------------------
            # 1) Determine starting column
            #     a) Prefer first free slot if we already know colspan via gridSpan
            #     b) Else fallback to width/position heuristic
            # ------------------------------------------------------------------
            colspan_attr = _grid_span(tc)
            logical_col = -1

            # Special case: if gridSpan covers all columns, always start at column 0
            if colspan_attr == num_cols:
                logical_col = 0
            else:
                # For partial spans, use first available slot
                logical_col = 0
                while logical_col < num_cols and grid[r][logical_col] is not None:
                    logical_col += 1
            
            # Safety check
            if logical_col >= num_cols:
                logger.warning(f"Row {r} TC{tc_idx}: could not fit cell into available columns")
                current_position += cell_width
                continue

            # Handle vertical merge
            vmerge = _vmerge_type(tc)
            colspan = colspan_attr

            # Width-only colspan inference when gridSpan is missing
            if colspan == 1 and tblGrid is not None and logical_col < num_cols:
                remaining_width = cell_width
                span_cols = 0
                idx = logical_col
                while idx < num_cols and remaining_width > col_widths[idx] - 50:
                    remaining_width -= col_widths[idx]
                    span_cols += 1
                    idx += 1
                colspan = max(1, span_cols)
            
            # Handle vertical merge
            if vmerge == 'continue':
                for i in range(colspan):
                    if logical_col + i < num_cols:
                        grid[r][logical_col + i] = "v-merged"
                current_position += cell_width
                continue

            # Find the actual _Cell object
            cell_obj = None
            try:
                for cell_in_row in row.cells:
                    if cell_in_row._tc == tc:
                        cell_obj = cell_in_row
                        break
                if not cell_obj:
                    # This might be an SDT-wrapped cell, create a _Cell object
                    try:
                        cell_obj = _Cell(tc, row)
                    except Exception as cell_creation_error:
                        logger.warning(f"Could not create _Cell for SDT-wrapped tc at R{r}C{tc_idx}: {cell_creation_error}")
                        current_position += cell_width
                        continue
            except Exception as e:
                logger.error(f"Error finding cell object at R{r}C{tc_idx}: {e}")
                current_position += cell_width
                continue

            # Place the cell
            cell_info = CellInfo(cell=cell_obj, colspan=colspan, is_start=True)
            grid[r][logical_col] = cell_info
            
            # Mark horizontal spans
            for i in range(1, colspan):
                if logical_col + i < num_cols:
                    grid[r][logical_col + i] = "h-merged"
            
            current_position += cell_width

        # Mark trailing omitted cells (gridAfter)
        for i in range(ga):
            if num_cols - 1 - i >= 0 and grid[r][num_cols - 1 - i] is None:
                grid[r][num_cols - 1 - i] = "omitted"

        # Convert any remaining None positions to omitted (missing trailing cells)
        for c in range(num_cols):
            if grid[r][c] is None:
                grid[r][c] = "omitted"

        row_idx += 1

    # --- 2. Calculate Rowspans ---
    num_rows = len(grid)
    for r in range(num_rows):
        for c in range(num_cols):
            cell_info = grid[r][c]
            if isinstance(cell_info, CellInfo) and cell_info.is_start:
                rowspan = 1
                # Check all columns this cell spans for vertical merges
                for i in range(r + 1, num_rows):
                    is_merged_row = all(
                        c + j < num_cols and grid[i][c + j] == "v-merged"
                        for j in range(cell_info.colspan)
                    )
                    if is_merged_row:
                        rowspan += 1
                    else:
                        break
                cell_info.rowspan = rowspan

    # --- 3. Generate DITA XML ---
    dita_table = ET.Element('table', id=generate_dita_id())
    tgroup = ET.SubElement(dita_table, 'tgroup', id=generate_dita_id(), cols=str(num_cols))

    # --- Colspecs with proportional widths ---
    total_width = sum(col_widths)
    for i in range(num_cols):
        if total_width > 0:
            pct_width = (col_widths[i] / total_width) * 100
            width_str = f"{pct_width:.2f}%"
        else:
            width_str = f"{100/num_cols:.1f}%"
        cs_attrs = {
            'colname': f'column-{i}',
            'colwidth': width_str,
            'colsep': '1',
            'rowsep': '1',
            'rowheader': 'headers',
        }
        ET.SubElement(tgroup, 'colspec', **cs_attrs)

    # --- Thead and Tbody ---
    header_rows = [r for r, row in enumerate(table.rows) if _is_header_row(row._tr)]
    has_header = len(header_rows) > 0

    # Determine if header rows form a contiguous prefix at the top
    def _is_contiguous_prefix(indices: list[int]) -> bool:
        if not indices:
            return False
        expected = list(range(min(indices), min(indices) + len(indices)))
        return indices == expected and min(indices) == 0

    headers_are_top_prefix = _is_contiguous_prefix(header_rows)

    thead = ET.SubElement(tgroup, 'thead', id=generate_dita_id()) if has_header and headers_are_top_prefix else None
    tbody = ET.SubElement(tgroup, 'tbody', id=generate_dita_id())

    for r_idx, grid_row in enumerate(grid):
        is_header = r_idx in header_rows
        row_parent = thead if (is_header and thead is not None) else tbody
        row_el = ET.SubElement(row_parent, 'row', id=generate_dita_id())
        # If we decided not to use thead (headers mid-table), mark header rows for preview styling
        if is_header and thead is None:
            row_el.set('outputclass', 'header-row')

        for c_idx, cell_info in enumerate(grid_row):
            if cell_info == "omitted" or cell_info is None:
                # Emit an explicit empty entry so column counts match
                empty_attrs = {
                    'colname': f'column-{c_idx}',
                    'colsep': '1',
                    'rowsep': '1',
                    'valign': 'middle' if is_header else 'top'
                }
                ET.SubElement(row_el, 'entry', **empty_attrs)
                continue

            if not (isinstance(cell_info, CellInfo) and cell_info.is_start):
                # Skip placeholders (merged continuations)
                continue

            attrs = {}
            if cell_info.rowspan > 1:
                attrs['morerows'] = str(cell_info.rowspan - 1)
            if cell_info.colspan > 1:
                start_idx = c_idx
                end_idx = min(c_idx + cell_info.colspan - 1, num_cols - 1)
                attrs['namest'] = f'column-{start_idx}'
                attrs['nameend'] = f'column-{end_idx}'
            else:
                # Single column cells should use colname
                attrs['colname'] = f'column-{c_idx}'
            
            # Add border attributes for proper rendering
            attrs['colsep'] = '1'
            attrs['rowsep'] = '1'
            
            # Add valign attribute (commonly used in reference)
            attrs['valign'] = 'middle' if is_header else 'top'

            entry_el = ET.SubElement(row_el, 'entry', **attrs)

            for p in cell_info.cell.paragraphs:
                p_el = ET.SubElement(entry_el, 'p', id=generate_dita_id())
                # Handle paragraphs that may contain SDT-wrapped content
                process_paragraph_content_and_images(p_el, p, image_map, None)

    # Prune empty thead
    if has_header and thead is not None and len(thead) == 0:
        tgroup.remove(thead)

    # Ensure tbody is present and non-empty to satisfy DITA DTD (colspec*, thead?, tbody)
    if tbody is not None and len(tbody) == 0:
        # Insert a single invisible placeholder row so the CALS model is respected
        placeholder_row = ET.SubElement(tbody, 'row', id=generate_dita_id())
        placeholder_row.set('outputclass', 'aux-empty')
        if num_cols > 1:
            entry_attrs = {
                'namest': 'column-0',
                'nameend': f'column-{num_cols - 1}',
                'colsep': '0',
                'rowsep': '0'
            }
            entry_el = ET.SubElement(placeholder_row, 'entry', **entry_attrs)
        else:
            entry_attrs = {
                'colname': 'column-0',
                'colsep': '0',
                'rowsep': '0'
            }
            entry_el = ET.SubElement(placeholder_row, 'entry', **entry_attrs)
        ET.SubElement(entry_el, 'p', id=generate_dita_id())

    return dita_table 

def log_grid(grid: list[list[Any]]):
    """Helper to log the logical grid structure for debugging."""
    logger.debug("--- Final Logical Grid ---")
    for r_idx, row in enumerate(grid):
        row_str = []
        for cell_info in row:
            if cell_info == "h-merged" or cell_info == "v-merged":
                row_str.append(f"[{cell_info.upper()}]")
            elif cell_info == "omitted":
                row_str.append("[OMITTED]")
            elif isinstance(cell_info, CellInfo) and cell_info.is_start:
                text = cell_info.cell.text.strip().replace('\\n', ' ')
                row_str.append(f"'{text[:15]}...' (c:{cell_info.colspan}, r:{cell_info.rowspan})")
            else: # Occupied by a span from another cell
                row_str.append("[SPAN]")
        logger.debug(f"Row {r_idx}: {' | '.join(row_str)}")
    logger.debug("--------------------------") 