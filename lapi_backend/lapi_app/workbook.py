"""Everything in a workbook, read and connected.

An .xlsx file is a package of parts. Lapi lists every part and gives each a reader, so nothing is
dropped silently: what cannot be read goes on the document's "Not read" list with the reason.

- Cells keep their values (spreadsheet.py), plus the formula behind them; a formula Excel never
  calculated (files made by scripts) is calculated here (pycel), or flagged when it cannot be.
- Comments (classic and threaded), hyperlinks, highlight colours and hidden rows go into the text of
  the row they belong to, so search, extraction and chat see them with the row.
- Images are read by the OCR vision model (text and a short description), charts become a small data
  table, text boxes and SmartArt give their text, embedded files (PDF, Word, Excel, images, text) are
  read like uploads. Each is anchored to its sheet, cell and row.
- Relationships are recorded: formula sources, chart data ranges, keys shared between sheets, items
  anchored to rows, and items whose text names a value in the table (an invoice number on a receipt).
  A proven link (formula, anchor, exact unique key) is marked "proven"; value overlap is "likely".
- A meaning profile per sheet (columns, types, ranges, the real values of label columns, formulas,
  dropdown lists, links) lets chat and extraction understand wording that is not a column name.
"""
import datetime as dt
import io
import math
import posixpath
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from . import spreadsheet

MAX_PARTS = 5_000
MAX_UNCOMPRESSED = 400 * 1024 * 1024
MAX_RATIO = 200                     # compressed/uncompressed: zip-bomb guard
MAX_IMAGES = 300
MAX_EMBEDDED = 50
MAX_EMBEDDED_BYTES = 40 * 1024 * 1024
FORMULA_SECONDS = 120
MAX_LINEAGE = 5_000
CATEGORY_LIMIT = 60                 # a column with at most this many distinct values lists them all

N = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
     'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
     'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
     'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
     'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
     'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
     'tc': 'http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments'}
R_ID = '{%s}id' % N['r']
R_EMBED = '{%s}embed' % N['r']

# Parts that only describe the package, styles or layout: read as structure, nothing to report.
STRUCTURE = re.compile(r'^(\[Content_Types\]\.xml|_rels/.*|docProps/.*|.*\.rels|xl/workbook\.xml|xl/styles\.xml|'
                       r'xl/theme/.*|xl/sharedStrings\.xml|xl/calcChain\.xml|xl/printerSettings/.*|xl/metadata\.xml|'
                       r'xl/charts/(style|colors)\d*\.xml|xl/drawings/vmlDrawing\d*\.vml|xl/persons/.*|'
                       r'xl/richData/.*|xl/worksheets/sheet\d+\.xml|xl/drawings/drawing\d+\.xml|xl/comments\d*\.xml|'
                       r'xl/threadedComments/.*|xl/media/.*|xl/charts/chart\d+\.xml|xl/embeddings/.*|xl/tables/.*|'
                       r'xl/pivotTables/.*|xl/pivotCache/.*|xl/externalLinks/.*|xl/vbaProject\.bin|'
                       r'xl/diagrams/.*|customXml/.*|xl/webextensions/.*)$', re.I)
NOT_READ = [  # (pattern, what it is, why it is not read)
    (r'^xl/connections\.xml$', 'data connections', 'connection definitions to outside data; Lapi uses the values saved in the cells'),
    (r'^xl/queryTables/', 'query table definitions', 'refresh settings for outside data; the imported values are read as cells'),
    (r'^xl/slicers/|^xl/slicerCaches/', 'slicers', 'filter buttons; the data they filter is read as cells'),
    (r'^xl/timelines/|^xl/timelineCaches/', 'timeline filters', 'filter controls; the data they filter is read as cells'),
    (r'^xl/ctrlProps/|^xl/activeX/', 'form controls', 'buttons and checkboxes on the sheet are not read'),
    (r'^xl/charts/chartEx\d*\.xml$', 'new-style charts (waterfall, treemap, funnel...)', 'their data ranges are read as cells; the chart itself is not drawn as a table'),
    (r'^xl/model/', 'Power Pivot data model', 'the data model inside the file is not read; only sheet cells are'),
]


class WorkbookError(spreadsheet.SpreadsheetError):
    pass


# --- Package helpers ----------------------------------------------------------------------------------

def _xml(z, part):
    try:
        return ET.fromstring(z.read(part))
    except (KeyError, ET.ParseError):
        return None


def _target(base, target):
    if target.startswith('/'):
        return target[1:]
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), target))


def _rels(z, part):
    """{rId: (absolute part or external target, relationship type, external?)}"""
    folder, name = posixpath.split(part)
    root = _xml(z, posixpath.join(folder, '_rels', name + '.rels'))
    out = {}
    for rel in (root.findall('rel:Relationship', N) if root is not None else []):
        external = rel.get('TargetMode') == 'External'
        out[rel.get('Id')] = (rel.get('Target') if external else _target(part, rel.get('Target', '')), rel.get('Type', '').rsplit('/', 1)[-1], external)
    return out


def _texts(node):
    return ' '.join(t.text.strip() for t in node.iter('{%s}t' % N['a']) if t.text and t.text.strip()) if node is not None else ''


def cell_ref(row, col):
    """1-based row and column to "C12"."""
    return spreadsheet._column_letter(col - 1) + str(row)


def check_package(raw):
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise WorkbookError('The workbook could not be opened. Save it again from Excel as .xlsx.')
    infos = z.infolist()
    if len(infos) > MAX_PARTS:
        raise WorkbookError(f'The workbook has more than {MAX_PARTS:,} internal parts. Save a simpler copy and upload that.')
    total = sum(i.file_size for i in infos)
    if total > MAX_UNCOMPRESSED or any(i.compress_size and i.file_size / i.compress_size > MAX_RATIO for i in infos if i.file_size > 1_000_000):
        raise WorkbookError('The workbook expands to an unsafe size. Save a smaller copy and upload that.')
    if any(i.flag_bits & 0x1 for i in infos):
        raise WorkbookError('The workbook is password protected. Remove the password in Excel and upload it again.')
    return z


# --- Cells: values, formulas, comments, links, colours ---------------------------------------------------

COLOURS = {'red': (255, 0, 0), 'orange': (255, 165, 0), 'yellow': (255, 255, 0), 'green': (0, 176, 80), 'light green': (198, 239, 206),
           'light red': (255, 199, 206), 'light yellow': (255, 235, 156), 'blue': (0, 112, 192), 'light blue': (189, 215, 238),
           'purple': (112, 48, 160), 'grey': (191, 191, 191), 'black': (0, 0, 0), 'white': (255, 255, 255)}


def colour_name(colour):
    """A plain colour name for an openpyxl colour, or '' for none/automatic/white."""
    if colour is None:
        return ''
    if getattr(colour, 'type', None) == 'theme':
        return f'theme colour {colour.theme}'
    if getattr(colour, 'type', None) == 'indexed':
        return '' if colour.indexed in (64, 65) else f'colour {colour.indexed}'
    rgb = getattr(colour, 'rgb', None)
    if not isinstance(rgb, str) or len(rgb) < 6:
        return ''
    r, g, b = (int(rgb[-6:][i:i + 2], 16) for i in (0, 2, 4))
    name = min(COLOURS, key=lambda k: sum((x - y) ** 2 for x, y in zip(COLOURS[k], (r, g, b))))
    return '' if name == 'white' else name


def _formula_text(value):
    if isinstance(value, str) and value.startswith('='):
        return value
    text = getattr(value, 'text', None)       # ArrayFormula
    return ('=' + text.lstrip('=')) if isinstance(text, str) else None


def _calculator(raw):
    """A lazy formula evaluator over the original file, or None when pycel is unavailable."""
    try:
        import tempfile, os
        from pycel import ExcelCompiler
        from pycel.excelformula import ExcelFormula
    except ImportError:
        return None
    if 'lapi_app.excel_functions' not in ExcelFormula.default_modules:   # COUNTA, XLOOKUP, TEXTJOIN, ...
        ExcelFormula.default_modules = ExcelFormula.default_modules + ('lapi_app.excel_functions',)
    handle, path = tempfile.mkstemp(suffix='.xlsx')
    with os.fdopen(handle, 'wb') as out:
        out.write(raw)
    try:
        return ExcelCompiler(filename=path)
    finally:
        try: os.unlink(path)
        except OSError: pass


def _plain(value):
    """A pycel result as a plain cell value (numbers, text, booleans); errors become None."""
    try:
        import numpy as np
        if isinstance(value, np.generic):
            value = value.item()
    except ImportError:
        pass
    if isinstance(value, (tuple, list)):
        return None
    if isinstance(value, str) and value.startswith('#'):
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def read_cells(raw, report):
    """[(sheet name, rows, notes, extras)] where extras holds formulas, notes per row, hidden rows,
    dropdown lists and highlight rules. Formulas without a saved result are calculated."""
    from openpyxl import load_workbook
    try:
        values = load_workbook(io.BytesIO(raw), data_only=True)
        formulas = load_workbook(io.BytesIO(raw), data_only=False)
    except Exception as exc:
        raise WorkbookError('The workbook could not be opened. Save it again from Excel as .xlsx.') from exc
    if len(values.worksheets) > spreadsheet.MAX_SHEETS:
        raise WorkbookError(f'The workbook has more than {spreadsheet.MAX_SHEETS} sheets. Split it or remove unused sheets.')
    calculator, started, calculated, failed = None, time.monotonic(), 0, []
    out = []
    for ws, wf in zip(values.worksheets, formulas.worksheets):
        notes = ['hidden sheet'] if ws.sheet_state != 'visible' else []
        filled = {}
        for merged in list(ws.merged_cells.ranges):
            value = ws.cell(merged.min_row, merged.min_col).value
            for r in range(merged.min_row, merged.max_row + 1):
                for c in range(merged.min_col, merged.max_col + 1):
                    filled[(r, c)] = value
        if filled:
            notes.append('merged cells were filled from their first cell')
        extras = {'formulas': {}, 'row_notes': {}, 'cell_notes': [], 'hidden_rows': [], 'hidden_columns': [],
                  'validations': [], 'highlight_rules': [], 'tables': []}
        rows = []
        for r, (vrow, frow) in enumerate(zip(ws.iter_rows(), wf.iter_rows()), start=1):
            row = []
            for c, (vcell, fcell) in enumerate(zip(vrow, frow), start=1):
                value = filled.get((r, c), vcell.value)
                formula = _formula_text(fcell.value)
                if formula:
                    extras['formulas'][cell_ref(r, c)] = formula
                    if value is None and (r, c) not in filled:
                        if time.monotonic() - started < FORMULA_SECONDS:
                            try:
                                calculator = calculator or _calculator(raw)
                                value = _plain(calculator.evaluate(f"'{ws.title}'!{cell_ref(r, c)}")) if calculator else None
                                calculated += value is not None
                            except Exception:
                                value = None
                        if value is None:
                            failed.append(f'{ws.title}!{cell_ref(r, c)}')
                row.append(value)
                cell_notes = []
                comment = getattr(fcell, 'comment', None)
                if comment is not None and comment.text and not comment.text.startswith('[Threaded comment]'):
                    cell_notes.append(f'note on {{column}}: {" ".join(comment.text.split())}' + (f' ({comment.author})' if comment.author else ''))
                link = getattr(fcell, 'hyperlink', None)
                if link is not None and (link.target or link.location):
                    cell_notes.append(f'link on {{column}}: {link.target or link.location}')
                fill = getattr(fcell, 'fill', None)
                if fill is not None and getattr(fill, 'fill_type', None) == 'solid' and (name := colour_name(fill.fgColor)):
                    cell_notes.append(f'{{column}} highlighted {name}')
                font = getattr(fcell, 'font', None)
                if font is not None and getattr(font.color, 'type', None) == 'rgb' and (name := colour_name(font.color)) not in ('', 'black'):  # theme text colour is the default
                    cell_notes.append(f'{{column}} written in {name}')
                if cell_notes:
                    extras['cell_notes'].append((r, c, cell_notes))
            rows.append(row)
        extras['hidden_rows'] = sorted(r for r, d in wf.row_dimensions.items() if d.hidden)
        extras['hidden_columns'] = sorted(k for k, d in wf.column_dimensions.items() if d.hidden)
        for dv in getattr(wf.data_validations, 'dataValidation', []):
            if dv.type == 'list' and dv.formula1:
                extras['validations'].append({'range': str(dv.sqref), 'allowed': dv.formula1.strip('"')})
        for cf_range in wf.conditional_formatting:
            for rule in cf_range.rules:
                detail = ' '.join(filter(None, [rule.type, rule.operator or '', ', '.join(rule.formula or []), rule.text or '']))
                extras['highlight_rules'].append({'range': str(cf_range.sqref), 'rule': detail.strip()})
        extras['tables'] = [{'name': name, 'range': ref} for name, ref in wf.tables.items()]
        out.append((ws.title, rows, notes, extras))
    report['calculated'] = calculated
    if failed:
        report['not_read'].append({'what': f'{len(failed)} formula result{"s" if len(failed) != 1 else ""}', 'where': ', '.join(failed[:10]) + (' …' if len(failed) > 10 else ''),
                                   'reason': 'Excel never saved a result and Lapi could not calculate it; open the file in Excel, save it, and upload it again'})
    names = []
    for name, defined in getattr(formulas, 'defined_names', {}).items():
        if not name.startswith('_xlnm'):
            names.append({'name': name, 'refers_to': defined.attr_text})
    report['names'] = names
    return out


# --- Drawings: images, charts, text boxes, SmartArt -------------------------------------------------------

def _anchor(node):
    for tag in ('from', 'to'):
        found = node.find(f'xdr:{tag}', N)
        if found is not None and tag == 'from':
            row = int(found.findtext('xdr:row', '0', N)) + 1
            col = int(found.findtext('xdr:col', '0', N)) + 1
            return row, col
    return None, None


def _shapes(node):
    """Leaf drawing objects under an anchor or group: (kind, element)."""
    for child in node:
        tag = child.tag.rsplit('}', 1)[-1]
        if tag == 'grpSp':
            yield from _shapes(child)
        elif tag in ('pic', 'graphicFrame', 'sp', 'cxnSp'):
            yield tag, child


def read_chart(root):
    """{'title', 'type', 'series': [{'name', 'categories', 'values', 'ranges'}]} from chart XML."""
    def cache(node):
        if node is None:
            return [], ''
        ref = node.findtext('.//c:f', '', N)
        points = {}
        for pt in node.iter('{%s}pt' % N['c']):
            points[int(pt.get('idx', '0'))] = pt.findtext('c:v', '', N)
        return [points[k] for k in sorted(points)], ref
    title_node = root.find('.//c:chart/c:title', N)
    title = _texts(title_node)
    plot = root.find('.//c:plotArea', N)
    kinds = [child.tag.rsplit('}', 1)[-1].replace('Chart', '') for child in (plot if plot is not None else []) if child.tag.endswith('Chart')]
    series = []
    for ser in root.iter('{%s}ser' % N['c']):
        name_values, name_ref = cache(ser.find('c:tx', N))
        name = name_values[0] if name_values else ser.findtext('c:tx/c:v', '', N)
        categories, cat_ref = cache(ser.find('c:cat', N) if ser.find('c:cat', N) is not None else ser.find('c:xVal', N))
        values, val_ref = cache(ser.find('c:val', N) if ser.find('c:val', N) is not None else ser.find('c:yVal', N))
        series.append({'name': name or f'Series {len(series) + 1}', 'categories': categories, 'values': values,
                       'ranges': [r for r in (name_ref, cat_ref, val_ref) if r]})
    return {'title': title or (', '.join(s['name'] for s in series) if series else 'Untitled chart'), 'type': ' / '.join(kinds) or 'chart', 'series': series}


def range_values(ref, grid):
    """Cell values of a reference like 'Sheet'!$A$2:$A$7 from the read grid, as display text."""
    m = REF.match(ref)
    if not m:
        return []
    rows = grid.get((m.group(1) or m.group(2)).replace("''", "'"))
    parts = re.findall(r'([A-Z]{1,3})(\d+)', m.group(3).replace('$', ''))
    if rows is None or not parts:
        return []
    (c1, r1), (c2, r2) = parts[0], parts[-1]
    out = []
    for r in range(int(r1), int(r2) + 1):
        for c in range(_col_index(c1), _col_index(c2) + 1):
            value = rows[r - 1][c - 1] if r - 1 < len(rows) and c - 1 < len(rows[r - 1]) else None
            out.append(spreadsheet._display(value))
    return out


def fill_chart(chart, grid):
    """Charts written by scripts have no saved numbers: read them from the cells they point to."""
    for series in chart['series']:
        refs = series['ranges']
        if not series['values'] and refs:
            series['values'] = range_values(refs[-1], grid)
        if not series['categories'] and len(refs) >= 2:
            series['categories'] = range_values(refs[-2], grid)
        if series['name'].startswith('Series') and len(refs) == 3:
            series['name'] = (range_values(refs[0], grid) or [series['name']])[0] or series['name']


def chart_text(chart):
    lines = [f'Chart "{chart["title"]}" ({chart["type"]} chart).']
    ranges = sorted({r for s in chart['series'] for r in s['ranges']})
    if ranges:
        lines.append('Data from ' + ', '.join(ranges) + '.')
    categories = next((s['categories'] for s in chart['series'] if s['categories']), [])
    if categories:
        lines.append(' | '.join(['Category'] + [s['name'] for s in chart['series']]))
        for i, category in enumerate(categories):
            lines.append(' | '.join([category] + [s['values'][i] if i < len(s['values']) else '' for s in chart['series']]))
    else:
        for s in chart['series']:
            lines.append(f'{s["name"]}: ' + ', '.join(s['values']))
    return '\n'.join(lines)


def _embedded_payload(name, raw):
    """(file name, bytes) of a file embedded in the workbook; OLE packages are unwrapped."""
    if not raw.startswith(b'\xd0\xcf\x11\xe0'):
        return posixpath.basename(name), raw
    try:
        import olefile
    except ImportError:
        return None
    try:
        ole = olefile.OleFileIO(io.BytesIO(raw))
        streams = ['/'.join(s) for s in ole.listdir()]
        if 'CONTENTS' in streams:                       # an embedded PDF
            return posixpath.splitext(posixpath.basename(name))[0] + '.pdf', ole.openstream('CONTENTS').read()
        if 'Package' in streams:                        # an embedded Office file
            data = ole.openstream('Package').read()
            return posixpath.splitext(posixpath.basename(name))[0] + ('.xlsx' if b'xl/' in data[:4000] else '.docx'), data
        if '\x01Ole10Native' in streams:                # "Packager": original name + bytes
            data = ole.openstream('\x01Ole10Native').read()
            body = data[4:]
            parts = body[2:].split(b'\x00', 2)
            original = parts[0].decode('latin-1') or 'embedded file'
            rest = parts[2] if len(parts) > 2 else b''
            rest = rest.split(b'\x00', 1)[1] if b'\x00' in rest[:600] else rest     # source path
            rest = rest[4:]                                                         # reserved
            size = int.from_bytes(rest[:4], 'little'); rest = rest[4:]
            rest = rest.split(b'\x00', 1)[1] if b'\x00' in rest[:size + 600] else rest   # temp path
            length = int.from_bytes(rest[:4], 'little')
            return original, rest[4:4 + length]
    except Exception:
        return None
    return None


def read_package(z, sheet_names, report, read_image, read_file, progress=None):
    """Items anchored in sheets (images, charts, text boxes, SmartArt, embedded files, threaded
    comments) and package-level facts. Every part is accounted for in the report."""
    workbook = _xml(z, 'xl/workbook.xml')
    wb_rels = _rels(z, 'xl/workbook.xml')
    sheet_parts = {}
    for sheet in (workbook.findall('main:sheets/main:sheet', N) if workbook is not None else []):
        target = wb_rels.get(sheet.get(R_ID))
        if target:
            sheet_parts[target[0]] = sheet.get('name')
    items, handled, threaded = [], set(), {}
    persons = {}
    for part in z.namelist():
        if part.startswith('xl/persons/'):
            root = _xml(z, part)
            for person in (root if root is not None else []):
                persons[person.get('id')] = person.get('displayName', '')
    images_seen = 0

    def add(item):
        item['id'] = f'{item["kind"]}-{sum(1 for i in items if i["kind"] == item["kind"]) + 1}'
        items.append(item)

    for part, sheet in sheet_parts.items():
        handled.add(part)
        rels = _rels(z, part)
        root = _xml(z, part)
        # Embedded objects declared on the sheet, with their anchor cells.
        for ole in (root.iter('{%s}oleObject' % N['main']) if root is not None else []):
            target = rels.get(ole.get(R_ID))
            anchor = ole.find('.//main:objectPr/main:anchor/main:from', N)
            row = int(anchor.findtext('xdr:row', '0', N)) + 1 if anchor is not None else None
            col = int(anchor.findtext('xdr:col', '0', N)) + 1 if anchor is not None else None
            if target and not target[2]:
                handled.add(target[0])
                add({'kind': 'embedded', 'sheet': sheet, 'row': row, 'col': col, 'part': target[0], 'program': ole.get('progId', '')})
        for rid, (target, kind, external) in rels.items():
            if external:
                continue
            if kind == 'drawing':
                handled.add(target)
                drawing = _xml(z, target)
                d_rels = _rels(z, target)
                for anchor in (drawing if drawing is not None else []):
                    row, col = _anchor(anchor)
                    for shape, node in _shapes(anchor):
                        props = node.find('.//xdr:cNvPr', N)
                        name, alt = (props.get('name', ''), props.get('descr', '')) if props is not None else ('', '')
                        if shape == 'pic':
                            blip = node.find('.//a:blip', N)
                            media = d_rels.get(blip.get(R_EMBED)) if blip is not None else None
                            if media and not media[2]:
                                handled.add(media[0])
                                add({'kind': 'image', 'sheet': sheet, 'row': row, 'col': col, 'part': media[0], 'name': name, 'alt': alt})
                        elif shape == 'graphicFrame':
                            data = node.find('.//a:graphicData', N)
                            uri = data.get('uri', '') if data is not None else ''
                            if uri.endswith('/chart'):
                                ref = data.find('c:chart', N)
                                chart = d_rels.get(ref.get(R_ID)) if ref is not None else None
                                if chart:
                                    handled.add(chart[0])
                                    root_chart = _xml(z, chart[0])
                                    if root_chart is not None:
                                        add({'kind': 'chart', 'sheet': sheet, 'row': row, 'col': col, 'part': chart[0], 'name': name, 'alt': alt, 'chart': read_chart(root_chart)})
                            elif uri.endswith('/diagram'):
                                ids = [v for k, v in data.find('*').attrib.items() if k.endswith('}dm')] if data.find('*') is not None else []
                                target_dm = d_rels.get(ids[0]) if ids else None
                                text = _texts(_xml(z, target_dm[0])) if target_dm else ''
                                add({'kind': 'text', 'sheet': sheet, 'row': row, 'col': col, 'name': name or 'SmartArt', 'text': text, 'shape': 'SmartArt'})
                            else:
                                report['not_read'].append({'what': 'drawing object', 'where': f'{sheet}!{cell_ref(row or 1, col or 1)}', 'reason': f'unsupported object type ({uri.rsplit("/", 1)[-1] or "unknown"})'})
                        elif shape == 'sp':
                            text = _texts(node.find('xdr:txBody', N))
                            if text or alt:
                                add({'kind': 'text', 'sheet': sheet, 'row': row, 'col': col, 'name': name, 'text': text or alt, 'shape': 'text box'})
            elif kind == 'threadedComment':
                handled.add(target)
                root_tc = _xml(z, target)
                for comment in (root_tc if root_tc is not None else []):
                    text = ' '.join((comment.findtext('tc:text', '', N) or '').split())
                    if text:
                        threaded.setdefault((sheet, comment.get('ref')), []).append(
                            text + (f' ({persons.get(comment.get("personId"))})' if persons.get(comment.get('personId')) else ''))
            elif kind == 'image':          # a sheet background picture
                handled.add(target)
                add({'kind': 'image', 'sheet': sheet, 'row': None, 'col': None, 'part': target, 'name': 'sheet background', 'alt': ''})
            elif kind == 'pivotTable':
                handled.add(target)
                pivot = _xml(z, target)
                location = pivot.find('main:location', N) if pivot is not None else None
                report['notes'].append(f'Pivot table "{pivot.get("name") if pivot is not None else ""}" on sheet {sheet}'
                                       + (f' at {location.get("ref")}' if location is not None else '') + ': its displayed values are read as cells.')
            elif kind in ('comments', 'table', 'vmlDrawing', 'printerSettings', 'oleObject', 'package', 'control', 'ctrlProp'):
                handled.add(target)
    # Read images and embedded files (the slow part: OCR and nested documents).
    total = sum(1 for i in items if i['kind'] == 'image')
    for item in items:
        if item['kind'] == 'image':
            images_seen += 1
            if images_seen > MAX_IMAGES:
                item['skipped'] = True
                continue
            if progress:
                progress(f'Reading image {images_seen} of {total} in the workbook')
            try:
                raw = z.read(item['part'])
            except KeyError:
                item['skipped'] = True; continue
            result = read_image(raw, item)
            item.update({k: result.get(k, '') for k in ('text', 'description', 'error')})
        elif item['kind'] == 'embedded':
            try:
                raw = z.read(item['part'])
            except KeyError:
                item['error'] = 'the embedded file is missing from the package'; continue
            if len(raw) > MAX_EMBEDDED_BYTES:
                item['error'] = 'the embedded file is larger than 40 MB'; continue
            payload = _embedded_payload(item['part'], raw)
            if not payload:
                item['error'] = f'an embedded {item.get("program") or "object"} that Lapi cannot open'; continue
            item['name'], data = payload
            if progress:
                progress(f'Reading embedded file {item["name"]}')
            try:
                item['text'] = read_file(item['name'], data)
            except Exception as exc:
                item['error'] = str(exc)[:200] if isinstance(exc, ValueError) else 'it could not be read'
    skipped = [i for i in items if i.get('skipped')]
    if skipped:
        report['not_read'].append({'what': f'{len(skipped)} image{"s" if len(skipped) != 1 else ""}', 'where': ', '.join(sorted({i["sheet"] for i in skipped})),
                                   'reason': f'Lapi reads up to {MAX_IMAGES} images per workbook'})
    for item in items:
        if item.get('error'):
            report['not_read'].append({'what': item['kind'] + (f' "{item.get("name")}"' if item.get('name') else ''), 'where': where(item), 'reason': item['error']})
    # Every other part: handled above, structure, a known "not read" kind, or unknown.
    for part in z.namelist():
        if part in handled or part.endswith('/'):
            continue
        if part == 'xl/vbaProject.bin':
            report['notes'].append('The workbook contains macros. Lapi read the data; the macro code was not run.')
            continue
        if part.startswith('xl/externalLinks/') and part.endswith('.xml'):
            for target, kind, external in _rels(z, part).values():
                if external:
                    report['notes'].append(f'Formulas refer to another workbook ({posixpath.basename(target)}); Lapi uses the values Excel saved for them.')
            continue
        known = next(((what, why) for pattern, what, why in NOT_READ if re.search(pattern, part)), None)
        if known:
            if not any(entry['what'] == known[0] for entry in report['not_read']):
                report['not_read'].append({'what': known[0], 'where': 'workbook', 'reason': known[1]})
            continue
        if part.startswith('xl/media/'):
            report['not_read'].append({'what': 'image not placed on any sheet', 'where': part, 'reason': 'it is stored in the file but not shown on a sheet'})
            continue
        if part.startswith('xl/embeddings/'):
            report['not_read'].append({'what': 'embedded file not placed on any sheet', 'where': part, 'reason': 'it is stored in the file but not shown on a sheet'})
            continue
        if STRUCTURE.match(part):
            continue
        report['not_read'].append({'what': 'unrecognised part', 'where': part, 'reason': 'Lapi does not know this kind of content yet'})
    return items, threaded


def where(item):
    return f'{item["sheet"]}!{cell_ref(item["row"], item["col"])}' if item.get('row') else f'sheet {item["sheet"]}'


# --- Relationships ------------------------------------------------------------------------------------------

REF = re.compile(r"(?:'((?:[^']|'')+)'|([A-Za-z_][\w\.]*))!(\$?[A-Z]{1,3}\$?\d*(?::\$?[A-Z]{1,3}\$?\d*)?)")
LOCAL = re.compile(r'(?<![!\w:$])\$?([A-Z]{1,3})\$?(\d+)(?![\w(])')
FUNCTION = re.compile(r'([A-Z][A-Z0-9\.]+)\(')
LOOKUPS = {'VLOOKUP', 'HLOOKUP', 'XLOOKUP', 'LOOKUP', 'INDEX', 'MATCH', 'XMATCH'}


def _column_names(sheet):
    """Column letter -> header name, for sheets read as tables."""
    return {spreadsheet._column_letter(i): name for i, name in enumerate(sheet['columns'])}


def _label(sheet_rows, row, col):
    """The nearest text to the left of a cell (a row label like "Total income"), else above."""
    values = dict(sheet_rows)
    current = values.get(row) or []
    for c in range(min(col - 1, len(current)) - 1, -1, -1):
        if isinstance(current[c], str) and current[c].strip():
            return current[c].strip()
    for r in range(row - 1, 0, -1):
        above = values.get(r) or []
        if col - 1 < len(above) and isinstance(above[col - 1], str) and above[col - 1].strip():
            return above[col - 1].strip()
    return ''


def formula_links(sheets, formulas):
    """Column formulas ("Amount (USD) = ROUND(Amount × FX Rate to USD, 2)"), per-cell lineage for the
    rest, and sheet-to-sheet links from formula references."""
    by_name = {s['name']: s for s in sheets}
    columns, lineage, links = {}, [], {}
    for sheet_name, cells in formulas.items():
        sheet = by_name.get(sheet_name)
        letters = _column_names(sheet) if sheet else {}
        patterns = {}
        for ref, formula in cells.items():
            letter, row = re.match(r'([A-Z]+)(\d+)', ref).groups()
            pattern = LOCAL.sub(lambda m: m.group(1) + ('{r}' if m.group(2) == row else m.group(2)), formula)
            patterns.setdefault(letter, {}).setdefault(pattern, []).append(ref)
            for match in REF.finditer(formula):
                target = (match.group(1) or match.group(2)).replace("''", "'")
                if target != sheet_name:
                    functions = set(FUNCTION.findall(formula))
                    key = (sheet_name, target)
                    entry = links.setdefault(key, {'kind': 'formula', 'from': sheet_name, 'to': target, 'cells': 0, 'functions': set(), 'ranges': set()})
                    entry['cells'] += 1; entry['functions'] |= functions; entry['ranges'].add(match.group(3))
        for letter, found in patterns.items():
            pattern, refs = max(found.items(), key=lambda kv: len(kv[1]))
            header = letters.get(letter)
            if header and len(refs) >= 3 and len(refs) >= 0.8 * sum(len(v) for v in found.values()):
                readable = re.sub(r'\b([A-Z]{1,3})\{r\}', lambda m: letters.get(m.group(1), m.group(1)), pattern)
                columns.setdefault(sheet_name, {})[header] = {'formula': pattern.replace('{r}', 'n'), 'meaning': readable, 'rows': len(refs)}
                found = {k: v for k, v in found.items() if k != pattern}
            for other in found.values():
                for ref in other:
                    if len(lineage) < MAX_LINEAGE:
                        letter_, row_ = re.match(r'([A-Z]+)(\d+)', ref).groups()
                        lineage.append({'sheet': sheet_name, 'cell': ref, 'formula': cells[ref],
                                        'row': int(row_), 'col': _col_index(letter_)})
    for entry in links.values():
        entry['functions'] = sorted(entry['functions']); entry['ranges'] = sorted(entry['ranges'])[:20]
        entry['lookup'] = bool(set(entry['functions']) & LOOKUPS)
        entry['strength'] = 'proven'
    return columns, lineage, list(links.values())


def _col_index(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _key_values(sheet, index):
    return [spreadsheet._display(row[index]).strip().lower() for _, row in sheet['rows'] if index < len(row) and not spreadsheet._empty(row[index])]


def key_links(sheets):
    """Columns whose values are the keys of another sheet (Transactions.Counterparty -> Vendors.Name)."""
    out = []
    for target in sheets:
        for ti, tname in enumerate(target['columns']):
            keys = _key_values(target, ti)
            if len(keys) < 3 or len(set(keys)) != len(keys):
                continue
            key_set = set(keys)
            for source in sheets:
                if source is target:
                    continue
                for si, sname in enumerate(source['columns']):
                    values = set(_key_values(source, si))
                    if len(values) < 2:
                        continue
                    share = len(values & key_set) / len(values)
                    if share >= 0.6:
                        out.append({'kind': 'key', 'from': source['name'], 'from_column': sname, 'to': target['name'], 'to_column': tname,
                                    'share': round(share, 3), 'strength': 'proven' if share >= 0.98 else 'likely'})
    return out


# Money-like numbers only (2 decimals or thousands separators), never the digits inside an ID like BILL-2025-0002.
AMOUNT = re.compile(r'(?<![\w.\-/])[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+\.\d{2})(?![\w.\-/])')


def _amounts(text):
    out = set()
    for match in AMOUNT.finditer(text or ''):
        try:
            out.add(round(float(re.sub(r'[,\s]', '', match.group())), 2))
        except ValueError:
            pass
    return out


def item_links(sheets, items):
    """Link items to rows: by anchor (proven) and by naming a table value (unique value: the row;
    repeated value: the value), and compare amounts with the row they belong to."""
    index = {}
    for sheet in sheets:
        for ci, column in enumerate(sheet['columns']):
            if sheet['kinds'][ci] != 'text':
                continue
            values = {}
            for number, row in sheet['rows']:
                value = row[ci].strip() if ci < len(row) and isinstance(row[ci], str) else ''
                # Distinctive values only: an identifier, a name of two words or more, or a long word.
                if len(value) >= 4 and (re.search(r'\d', value) or ' ' in value or len(value) >= 10):
                    values.setdefault(value, []).append(number)
            if len(values) > 20_000:
                continue
            for value, numbers in values.items():
                index.setdefault(value.lower(), []).append((sheet['name'], column, numbers))
    by_name = {s['name']: s for s in sheets}
    for item in items:
        text = ' '.join(filter(None, [item.get('text'), item.get('description'), item.get('alt')])).lower()
        links = []
        if item.get('row') and item['kind'] != 'chart':
            sheet = by_name.get(item['sheet'])
            if sheet and any(n == item['row'] for n, _ in sheet['rows']):
                links.append({'sheet': item['sheet'], 'row': item['row'], 'how': f'placed in row {item["row"]}', 'strength': 'proven'})
        if text:
            for value, places in index.items():
                if value in text and re.search(r'(?<!\w)' + re.escape(value) + r'(?!\w)', text):
                    for sheet_name, column, numbers in places:
                        if len(numbers) == 1:
                            links.append({'sheet': sheet_name, 'row': numbers[0], 'how': f'shows {column} "{value}"', 'strength': 'proven'})
                        else:
                            links.append({'sheet': sheet_name, 'value': value, 'column': column, 'rows': len(numbers), 'how': f'mentions {column} "{value}" ({len(numbers)} rows)', 'strength': 'likely'})
        seen, unique = set(), []
        for link in links:
            key = (link['sheet'], link.get('row'), link.get('value'))
            if key not in seen:
                seen.add(key); unique.append(link)
        item['links'] = unique[:20]
        # Agreement: amounts in the image against the numbers of each row it belongs to.
        found = _amounts(item.get('text'))
        for link in item['links']:
            sheet = by_name.get(link['sheet'])
            if not link.get('row') or not sheet or not found:
                continue
            row = next((values for n, values in sheet['rows'] if n == link['row']), [])
            numbers = {sheet['columns'][i]: round(spreadsheet._number(v), 2) for i, v in enumerate(row)
                       if sheet['kinds'][i] == 'number' and spreadsheet._number(v) is not None}
            money = {k: v for k, v in numbers.items() if v and (v != int(v) or abs(v) >= 100)}
            agree = sorted(k for k, v in money.items() if v in found)
            link['agrees'] = agree
            if money and not agree:
                link['differs'] = {'row': {k: v for k, v in list(money.items())[:4]}, 'item': sorted(found)[:6]}
    return items


# --- Meaning profiles ------------------------------------------------------------------------------------

def profile(sheet, extras, column_formulas, links, items):
    columns = []
    for i, (name, kind) in enumerate(zip(sheet['columns'], sheet['kinds'])):
        values = [row[i] for _, row in sheet['rows'] if i < len(row) and not spreadsheet._empty(row[i])]
        column = {'name': name, 'type': kind, 'filled': len(values)}
        if kind == 'number' and values:
            numbers = [spreadsheet._number(v) for v in values]
            column.update(min=min(numbers), max=max(numbers), total=round(sum(numbers), 6))
        elif kind == 'date' and values:
            dates = sorted(spreadsheet._date(v) for v in values)
            column.update(earliest=dates[0].date().isoformat(), latest=dates[-1].date().isoformat())
        else:
            distinct = list(dict.fromkeys(spreadsheet._display(v) for v in values))
            column['distinct'] = len(distinct)
            if 0 < len(distinct) <= CATEGORY_LIMIT and len(distinct) < max(2, len(values)):
                column['values'] = distinct
            else:
                column['examples'] = distinct[:5]
            column['unique'] = len(distinct) == len(values) and len(values) > 1
        if name in column_formulas:
            column['formula'] = column_formulas[name]['meaning']
        for validation in extras.get('validations', []):
            letter = spreadsheet._column_letter(i)
            if re.search(r'(?<![A-Z])' + letter + r'\d', validation['range']):
                column['allowed'] = validation['allowed']
        columns.append(column)
    related = [l for l in links if sheet['name'] in (l.get('from'), l.get('to'))]
    attached = {}
    for item in items:
        if item['sheet'] == sheet['name']:
            attached[item['kind']] = attached.get(item['kind'], 0) + 1
    return {'sheet': sheet['name'], 'rows': len(sheet['rows']), 'columns': columns, 'links': related, 'attached': attached,
            'hidden_rows': len(extras.get('hidden_rows', [])), 'highlight_rules': extras.get('highlight_rules', [])[:20],
            'notes': sheet.get('notes', [])}


def profile_text(p):
    lines = [f'Meaning profile of sheet "{p["sheet"]}": {p["rows"]:,} rows.']
    for c in p['columns']:
        detail = c['type']
        if 'values' in c:
            detail += ' with values: ' + ', '.join(c['values'])
        elif c.get('examples'):
            detail += ', e.g. ' + '; '.join(c['examples'])
        if 'min' in c:
            detail += f', from {spreadsheet._display(c["min"])} to {spreadsheet._display(c["max"])}, total {spreadsheet._display(c["total"])}'
        if 'earliest' in c:
            detail += f', {c["earliest"]} to {c["latest"]}'
        if c.get('unique'):
            detail += ', unique per row (an identifier)'
        if c.get('formula'):
            detail += f'; calculated as {c["formula"]}'
        if c.get('allowed'):
            detail += f'; dropdown: {c["allowed"]}'
        lines.append(f'- {c["name"]}: {detail}')
    for link in p['links']:
        if link['kind'] == 'key':
            lines.append(f'- Link ({link["strength"]}): {link["from"]}.{link["from_column"]} refers to {link["to"]}.{link["to_column"]}.')
        else:
            lines.append(f'- Link (formulas): {link["from"]} uses {link["to"]} ({", ".join(link["functions"]) or "references"}).')
    if p['attached']:
        lines.append('- Attached: ' + ', '.join(f'{v} {k}{"s" if v != 1 else ""}' for k, v in p['attached'].items()) + '.')
    for rule in p['highlight_rules'][:5]:
        lines.append(f'- Highlight rule on {rule["range"]}: {rule["rule"]}.')
    return '\n'.join(lines)


# --- The whole workbook --------------------------------------------------------------------------------------

def read(name, raw, *, read_image=None, read_file=None, progress=None):
    """{'sheets', 'items', 'links', 'lineage', 'profiles', 'coverage'} for an .xlsx, CSV or TSV file."""
    report = {'not_read': [], 'notes': [], 'calculated': 0, 'names': []}
    if not name.lower().endswith('.xlsx'):
        sheets = spreadsheet.read(name, raw)
        for sheet in sheets:
            sheet['extras'] = {}
        rows = spreadsheet._csv_rows(name, raw)
        width = max((len(r) for r in rows), default=0)
        ragged = [i for i, r in enumerate(rows, start=1) if r and any(v.strip() for v in r) and len(r) != width]
        if ragged:
            report['notes'].append(f'{len(ragged)} line{"s" if len(ragged) != 1 else ""} (e.g. line {ragged[0]}) had fewer cells than the widest line; missing cells were left empty, nothing was dropped.')
        book = {'sheets': sheets, 'items': [], 'links': key_links(sheets), 'lineage': [], 'column_formulas': {}}
    else:
        z = check_package(raw)
        cells = read_cells(raw, report)
        sheets, extras_by = [], {}
        for title, rows, notes, extras in cells:
            sheet = spreadsheet._sheet(title, rows, notes)
            if sheet:
                sheet['extras'] = extras
                sheets.append(sheet)
        if not sheets:
            raise WorkbookError('The spreadsheet has no data.')
        total = sum(len(s['rows']) for s in sheets)
        if total > spreadsheet.MAX_ROWS:
            raise WorkbookError(f'The spreadsheet has {total:,} data rows; Lapi reads up to {spreadsheet.MAX_ROWS:,}. Split it into smaller files.')
        items, threaded = read_package(z, [s['name'] for s in sheets], report, read_image or (lambda raw, item: {}), read_file or (lambda n, d: ''), progress)
        column_formulas, lineage, flinks = formula_links(sheets, {s['name']: s['extras']['formulas'] for s in sheets})
        by_name = {s['name']: s for s in sheets}
        rows_of = {s['name']: dict(s['rows']) for s in sheets}
        for entry in lineage:
            sheet = by_name[entry['sheet']]
            entry['label'] = _label(sheet['rows'], entry['row'], entry['col'])
            values = rows_of[entry['sheet']].get(entry['row']) or []
            entry['value'] = spreadsheet._display(values[entry['col'] - 1]) if entry['col'] - 1 < len(values) else ''
        for (sheet_name, ref), comments in threaded.items():
            m = re.match(r'([A-Z]+)(\d+)', ref or '')
            if m and sheet_name in by_name:
                by_name[sheet_name]['extras']['cell_notes'].append((int(m.group(2)), _col_index(m.group(1)), [f'comment on {{column}}: {c}' for c in comments]))
        grid = {title: rows for title, rows, _, _ in cells}
        for item in items:
            if item['kind'] == 'chart':
                fill_chart(item['chart'], grid)
                for series in item['chart']['series']:
                    for ref in series['ranges']:
                        m = REF.match(ref)
                        if m:
                            flinks.append({'kind': 'chart', 'from': item['sheet'], 'to': (m.group(1) or m.group(2)).replace("''", "'"), 'item': item['id'],
                                           'ranges': [m.group(3)], 'functions': [], 'strength': 'proven'})
        book = {'sheets': sheets, 'items': item_links(sheets, items), 'links': flinks + key_links(sheets), 'lineage': lineage,
                'column_formulas': column_formulas, 'names': report['names']}
        attach_notes(book)
    book['profiles'] = [profile(s, s.get('extras', {}), book['column_formulas'].get(s['name'], {}), book['links'], book['items']) for s in book['sheets']]
    book['coverage'] = coverage(book, report)
    return book


def attach_notes(book):
    """Comments, links, colours, hidden rows and attached items into the text of their row."""
    for sheet in book['sheets']:
        extras = sheet['extras']
        numbers = {n for n, _ in sheet['rows']}
        notes, outside = {}, []
        for row, col, texts in extras.get('cell_notes', []):
            column = sheet['columns'][col - 1] if 0 < col <= len(sheet['columns']) else f'column {spreadsheet._column_letter(col - 1)}'
            lines = [t.replace('{column}', column) for t in texts]
            (notes.setdefault(row, []).extend(lines) if row in numbers else outside.extend(f'{cell_ref(row, col)}: {t}' for t in lines))
        for row in extras.get('hidden_rows', []):
            if row in numbers:
                notes.setdefault(row, []).append('hidden row')
        for item in book['items']:
            for link in item.get('links', []):
                if link['sheet'] == sheet['name'] and link.get('row') in numbers:
                    summary = item_summary(item, short=True)
                    notes.setdefault(link['row'], []).append(f'{item["kind"]} {where(item)} ({link["how"]}): {summary}')
        sheet['row_notes'] = notes
        sheet['outside_notes'] = outside


def item_summary(item, short=False):
    if item['kind'] == 'chart':
        return chart_text(item['chart'])
    parts = []
    if item.get('description'):
        parts.append(item['description'])
    if item.get('alt'):
        parts.append(f'alt text: {item["alt"]}')
    if item.get('text'):
        text = ' '.join(item['text'].split())
        parts.append(('text: ' + (text[:300] + '…' if short and len(text) > 300 else text)))
    return '; '.join(parts) or ('could not be read: ' + item['error'] if item.get('error') else 'no readable content')


def item_pages(book, start):
    """Searchable pages: one per item, the workbook map, cell notes outside tables and profiles."""
    index = {s['name']: i for i, s in enumerate(book['sheets'], start=1)}
    pages = []
    for item in book['items']:
        if item.get('skipped'):
            continue
        links = '; '.join(f'{l["how"]} ({l["strength"]})' + (f', agrees on {", ".join(l["agrees"])}' if l.get('agrees') else '')
                          + (f', DIFFERS: row {l["differs"]["row"]} vs {l["differs"]["item"]}' if l.get('differs') else '') for l in item.get('links', []))
        label = {'image': 'Image', 'chart': 'Chart', 'text': item.get('shape', 'Text box').capitalize(), 'embedded': 'Embedded file'}[item['kind']]
        head = f'{label} {item.get("name") or item["id"]} on sheet {item["sheet"]}' + (f' at {cell_ref(item["row"], item["col"])}' if item.get('row') else '') + '.'
        pages.append({'page': index.get(item['sheet'], start), 'sheet': item['sheet'], 'section': f'Sheet: {item["sheet"]} · {label.lower()} {item["id"]}',
                      'workbook_item': item['id'], 'text': '\n'.join(filter(None, [head, item_summary(item), 'Connected: ' + links if links else ''])),
                      **({'text_origin': 'ocr', 'ocr': item['ocr'] | {'page': index.get(item['sheet'], start)}} if item.get('ocr') else {})})
    for sheet in book['sheets']:
        if sheet.get('outside_notes'):
            pages.append({'page': index[sheet['name']], 'sheet': sheet['name'], 'section': f'Sheet: {sheet["name"]} · notes',
                          'text': f'Notes on sheet {sheet["name"]}:\n' + '\n'.join(sheet['outside_notes'])})
    for p in book['profiles']:
        pages.append({'page': index[p['sheet']], 'sheet': p['sheet'], 'section': f'Sheet: {p["sheet"]} · meaning', 'text': profile_text(p)})
    if book.get('lineage'):
        lines = [f'{e["sheet"]}!{e["cell"]}' + (f' ("{e["label"]}")' if e.get('label') else '') + f' = {e["value"]} from {e["formula"]}' for e in book['lineage'][:400]]
        pages.append({'page': start, 'section': 'Workbook · calculated cells', 'text': 'Calculated cells and where they come from:\n' + '\n'.join(lines)})
    pages.append({'page': start, 'section': 'Workbook · what was read', 'text': coverage_text(book['coverage'])})
    return pages


def coverage(book, report):
    items = book['items']
    count = lambda kind: sum(1 for i in items if i['kind'] == kind and not i.get('error') and not i.get('skipped'))
    read = {'sheets': len(book['sheets']), 'rows': sum(len(s['rows']) for s in book['sheets']),
            'formulas': sum(len(s.get('extras', {}).get('formulas', {})) for s in book['sheets']), 'formulas calculated by Lapi': report['calculated'],
            'comments and notes': sum(1 for s in book['sheets'] for _, _, t in s.get('extras', {}).get('cell_notes', []) for x in t if x.startswith(('note on', 'comment on'))),
            'images': count('image'), 'charts': count('chart'), 'text boxes': count('text'), 'embedded files': count('embedded'),
            'links between parts': len(book['links']) + sum(len(i.get('links', [])) for i in items),
            'hidden rows': sum(len(s.get('extras', {}).get('hidden_rows', [])) for s in book['sheets'])}
    mismatches = [f'{i["kind"]} {where(i)} vs {l["sheet"]} row {l["row"]}' for i in items for l in i.get('links', []) if l.get('differs')]
    return {'read': {k: v for k, v in read.items() if v}, 'not_read': report['not_read'], 'notes': report['notes'] + [n for s in book['sheets'] for n in s.get('notes', []) if n],
            'mismatches': mismatches[:50], 'complete': not report['not_read']}


def coverage_text(c):
    lines = ['What Lapi read in this workbook: ' + ', '.join(f'{v:,} {k}' for k, v in c['read'].items()) + '.']
    if c['not_read']:
        lines.append('Not read: ' + '; '.join(f'{n["what"]} ({n["where"]}): {n["reason"]}' for n in c['not_read']) + '.')
    else:
        lines.append('Nothing was left unread.')
    if c['mismatches']:
        lines.append('Values that disagree: ' + '; '.join(c['mismatches']) + '.')
    lines.extend(c['notes'])
    return '\n'.join(lines)


def manifest_key(document_id):
    return f'documents/{document_id}/workbook.json'


def save(store, document_id, book):
    """The map without the cell rows (those are in the Parquet tables)."""
    sheets = [{'name': s['name'], 'columns': s['columns'], 'kinds': s['kinds'], 'notes': s.get('notes', []),
               'row_notes': {str(k): v for k, v in s.get('row_notes', {}).items()},
               'formulas': s.get('extras', {}).get('formulas', {}), 'validations': s.get('extras', {}).get('validations', []),
               'highlight_rules': s.get('extras', {}).get('highlight_rules', []), 'hidden_rows': s.get('extras', {}).get('hidden_rows', []),
               'tables': s.get('extras', {}).get('tables', [])} for s in book['sheets']]
    items = [{k: v for k, v in i.items() if k != 'part'} for i in book['items']]
    store.put_json(manifest_key(document_id), {'sheets': sheets, 'items': items, 'links': book['links'], 'lineage': book['lineage'],
                                               'column_formulas': book['column_formulas'], 'names': book.get('names', []),
                                               'profiles': book['profiles'], 'coverage': book['coverage']})


def load(store, document_id):
    try:
        return store.json(manifest_key(document_id))
    except (FileNotFoundError, KeyError, OSError):
        return None
