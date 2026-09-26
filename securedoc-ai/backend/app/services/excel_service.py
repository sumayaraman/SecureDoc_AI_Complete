import os
import re
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Positive invoice signal terms categorized
SIGNAL_INVOICE_IDS = [
    'invoice', 'tax invoice', 'invoice no', 'invoice number', 'invoice #', 
    'inv #', 'inv no', 'bill no', 'bill number', 'billing statement', 'commercial invoice'
]
SIGNAL_ENTITIES = [
    'bill to', 'billed to', 'ship to', 'vendor', 'supplier', 'seller', 
    'remit to', 'customer', 'sold to', 'client name'
]
SIGNAL_TABLE_HEADERS = [
    'description', 'item', 'details', 'particulars', 'service', 'product',
    'qty', 'quantity', 'unit price', 'unit cost', 'price', 'rate', 
    'amount', 'line total', 'total price', 'ext price'
]
SIGNAL_TOTALS = [
    'subtotal', 'sub-total', 'tax', 'vat', 'gst', 'discount', 
    'grand total', 'total due', 'amount due', 'balance due', 'net total', 'shipping'
]

# Negative signals: non-invoice spreadsheets
NEGATIVE_SIGNALS = {
    'monitoring': ['url', 'response time', 'http code', 'status code', 'uptime', 'latency', 'ping', 'endpoint', 'dns time'],
    'hr': ['employee id', 'department', 'designation', 'salary slip', 'leave balance', 'hire date', 'payroll id'],
    'analytics': ['metric', 'epoch', 'accuracy', 'precision', 'recall', 'f1-score', 'loss', 'dataset', 'confusion matrix'],
    'inventory_only': ['stock on hand', 'reorder level', 'warehouse bin', 'aisle', 'shelf location']
}

def clean_cell_str(val: Any) -> str:
    if val is None:
        return ''
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.strftime('%Y-%m-%d')
    return str(val).strip()

def parse_number(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(',', '')
    # Strip currency symbols
    s = re.sub(r'^[৳$€£¥\s]+', '', s)
    s = re.sub(r'[৳$€£¥\s]+$', '', s)
    try:
        return float(s)
    except (ValueError, TypeError):
        return None

def validate_and_read_excel(file_path: str) -> Dict[str, Any]:
    """
    Validates and reads an Excel workbook (.xlsx / .xls).
    Catches corrupted, password-protected, empty, or unreadable files safely.
    """
    p = Path(file_path)
    if not p.exists() or p.stat().st_size == 0:
        return {'success': False, 'error': 'Unable to read this Excel file. The file is empty or missing.'}

    if p.stat().st_size > 10 * 1024 * 1024:
        return {'success': False, 'error': 'Excel file exceeds 10 MB maximum allowed size.'}

    try:
        import openpyxl
        # Read workbook safely without executing macros or VBA
        wb = openpyxl.load_workbook(file_path, data_only=True, keep_vba=False)
    except Exception as e:
        # Check for password/encryption or corrupted zip
        err_msg = str(e).lower()
        if 'encrypted' in err_msg or 'password' in err_msg:
            return {'success': False, 'error': 'Unable to read this Excel file. It appears to be password-protected.'}
        return {'success': False, 'error': 'Unable to read this Excel file.'}

    sheets_data: Dict[str, List[List[Any]]] = {}
    total_cells = 0
    non_empty_cells = 0

    try:
        for name in wb.sheetnames:
            ws = wb[name]
            rows: List[List[Any]] = []
            for row in ws.iter_rows(values_only=True):
                cleaned_row = [c for c in row]
                rows.append(cleaned_row)
                for c in cleaned_row:
                    total_cells += 1
                    if c is not None and str(c).strip():
                        non_empty_cells += 1
            sheets_data[name] = rows
        wb.close()
    except Exception:
        return {'success': False, 'error': 'Unable to read this Excel file.'}

    if non_empty_cells < 2:
        return {'success': False, 'error': 'Unable to read this Excel file. The workbook contains no meaningful data.'}

    return {
        'success': True,
        'sheets': sheets_data,
        'sheet_names': list(sheets_data.keys()),
        'total_cells': total_cells,
        'non_empty_cells': non_empty_cells,
        'error': None
    }

def score_invoice_likelihood(sheets_data: Dict[str, List[List[Any]]], filename: str) -> Dict[str, Any]:
    """
    Determines whether the workbook contains invoice-like information.
    Uses multi-signal heuristic evaluation and rejects arbitrary spreadsheets.
    """
    all_text_lines: List[str] = [filename.lower()]
    for sheet_name, rows in sheets_data.items():
        all_text_lines.append(sheet_name.lower())
        for row in rows[:60]: # inspect first 60 rows of each sheet
            line_str = ' '.join(clean_cell_str(c).lower() for c in row if c is not None)
            if line_str:
                all_text_lines.append(line_str)
    
    combined_text = '\n'.join(all_text_lines)

    # 1. Check negative signals
    negative_matches: Dict[str, int] = {}
    for cat, terms in NEGATIVE_SIGNALS.items():
        matches = [t for t in terms if t in combined_text]
        if matches:
            negative_matches[cat] = len(matches)

    # 2. Check positive signals across categories
    matched_ids = [s for s in SIGNAL_INVOICE_IDS if s in combined_text]
    matched_entities = [s for s in SIGNAL_ENTITIES if s in combined_text]
    matched_headers = [s for s in SIGNAL_TABLE_HEADERS if s in combined_text]
    matched_totals = [s for s in SIGNAL_TOTALS if s in combined_text]

    # Heuristic scoring
    score = 0.0
    categories_hit = 0

    if matched_ids:
        score += min(40.0, len(matched_ids) * 20.0)
        categories_hit += 1
    if matched_entities:
        score += min(25.0, len(matched_entities) * 12.5)
        categories_hit += 1
    if matched_headers:
        score += min(25.0, len(matched_headers) * 8.0)
        categories_hit += 1
    if matched_totals:
        score += min(20.0, len(matched_totals) * 10.0)
        categories_hit += 1

    # Check for strong negative dominance (e.g. website monitoring)
    total_negative = sum(negative_matches.values())
    if total_negative >= 2 and len(matched_ids) == 0 and len(matched_entities) == 0:
        return {
            'is_supported': False,
            'doc_type': 'unsupported_spreadsheet',
            'score': 0.0,
            'reason': "This Excel file could be opened successfully, but we couldn't identify it as an invoice.",
            'details': f"Detected non-invoice dataset signals: {', '.join(negative_matches.keys())}"
        }

    # An invoice must meet score threshold and have multiple corroborating signal categories
    if score >= 45.0 and categories_hit >= 2:
        return {
            'is_supported': True,
            'doc_type': 'invoice',
            'score': min(98.0, score),
            'reason': 'Invoice signals verified across metadata, line items, and financial totals.',
            'categories_matched': categories_hit
        }

    return {
        'is_supported': False,
        'doc_type': 'unsupported_spreadsheet',
        'score': score,
        'reason': "This Excel file could be opened successfully, but we couldn't identify it as an invoice.",
        'details': "Spreadsheet lacks required invoice headers, line-item pricing table, or billing totals."
    }

def find_primary_invoice_sheet(sheets_data: Dict[str, List[List[Any]]]) -> Tuple[str, List[List[Any]]]:
    """Finds the most relevant invoice sheet in the workbook."""
    best_sheet = list(sheets_data.keys())[0]
    best_score = -1.0

    for name, rows in sheets_data.items():
        sheet_text = f"{name}\n" + '\n'.join(' '.join(clean_cell_str(c).lower() for c in r) for r in rows[:40])
        score = 0.0
        if any(w in name.lower() for w in ['invoice', 'bill', 'tax', 'receipt']):
            score += 30.0
        score += sum(10 for s in SIGNAL_INVOICE_IDS if s in sheet_text)
        score += sum(5 for s in SIGNAL_TOTALS if s in sheet_text)
        score += sum(5 for s in SIGNAL_TABLE_HEADERS if s in sheet_text)
        if score > best_score:
            best_score = score
            best_sheet = name

    return best_sheet, sheets_data[best_sheet]

def parse_line_items_from_grid(grid: List[List[Any]]) -> Tuple[List[Dict[str, Any]], Optional[int], Optional[int]]:
    """
    Dynamically locates the line-items table and extracts all rows.
    Handles 5, 10, 20, 50+ line items without stopping prematurely.
    """
    header_row_idx = None
    col_desc = None
    col_qty = None
    col_unit_price = None
    col_total = None
    col_discount = None
    col_tax = None

    # Step 1: Detect header row
    for r_idx, row in enumerate(grid[:40]):
        row_lower = [clean_cell_str(c).lower() for c in row]
        row_str = ' '.join(row_lower)
        
        has_desc = any(w in row_str for w in ['description', 'desc', 'particulars', 'item description', 'product', 'details', 'service'])
        has_qty = any(w in row_str for w in ['qty', 'quantity', 'count', 'hrs', 'hours', 'units'])
        has_price = any(w in row_str for w in ['unit price', 'price', 'rate', 'unit cost', 'price/unit'])
        has_amount = any(w in row_str for w in ['amount', 'line total', 'total price', 'total', 'ext price', 'subtotal'])

        if (has_desc and (has_qty or has_price or has_amount)) or (has_qty and has_price):
            header_row_idx = r_idx
            for c_idx, cell_str in enumerate(row_lower):
                if any(w == cell_str or f' {w}' in cell_str or f'{w} ' in cell_str for w in ['description', 'desc', 'particulars', 'item description', 'product', 'details', 'service', 'item']):
                    if col_desc is None: col_desc = c_idx
                elif any(w == cell_str or f' {w}' in cell_str or f'{w} ' in cell_str for w in ['qty', 'quantity', 'units', 'hours']):
                    if col_qty is None: col_qty = c_idx
                elif any(w == cell_str or f' {w}' in cell_str or f'{w} ' in cell_str for w in ['unit price', 'price', 'rate', 'unit cost']):
                    if col_unit_price is None: col_unit_price = c_idx
                elif any(w == cell_str or f' {w}' in cell_str or f'{w} ' in cell_str for w in ['total', 'amount', 'line total', 'total price', 'ext price']):
                    if col_total is None: col_total = c_idx
                elif any(w in cell_str for w in ['discount', 'disc']):
                    if col_discount is None: col_discount = c_idx
                elif any(w in cell_str for w in ['tax', 'vat']):
                    if col_tax is None: col_tax = c_idx
            break

    if header_row_idx is None:
        return [], None, None

    # Step 2: Read line items
    items: List[Dict[str, Any]] = []
    consecutive_empty = 0
    end_row_idx = header_row_idx + 1

    summary_keywords = ['subtotal', 'sub total', 'total due', 'grand total', 'balance due', 'tax (', 'vat (', 'terms & conditions', 'payment instructions', 'notes:', 'thank you']

    for r_idx in range(header_row_idx + 1, len(grid)):
        row = grid[r_idx]
        row_str = ' '.join(clean_cell_str(c).lower() for c in row)

        # Check if we hit summary rows
        if any(sw in row_str for sw in summary_keywords):
            end_row_idx = r_idx
            break

        # Check empty row
        if not any(c is not None and str(c).strip() for c in row):
            consecutive_empty += 1
            if consecutive_empty >= 3 and len(items) > 0:
                end_row_idx = r_idx
                break
            continue
        else:
            consecutive_empty = 0

        # Description
        desc = ''
        if col_desc is not None and col_desc < len(row):
            desc = clean_cell_str(row[col_desc])
        if not desc:
            # Fallback to first non-empty text cell
            for c in row:
                s = clean_cell_str(c)
                if s and parse_number(s) is None and len(s) > 1:
                    desc = s
                    break

        if not desc or len(desc) < 2 or any(k in desc.lower() for k in ['subtotal', 'grand total', 'tax']):
            continue

        # Quantity
        qty = 1.0
        if col_qty is not None and col_qty < len(row):
            q_num = parse_number(row[col_qty])
            if q_num is not None and q_num > 0:
                qty = q_num

        # Unit price & Total
        unit_price = 0.0
        if col_unit_price is not None and col_unit_price < len(row):
            p_num = parse_number(row[col_unit_price])
            if p_num is not None:
                unit_price = p_num

        total = 0.0
        if col_total is not None and col_total < len(row):
            t_num = parse_number(row[col_total])
            if t_num is not None:
                total = t_num

        # Reconcile if one of price/total was formula-based or empty
        if total == 0.0 and unit_price > 0.0:
            total = round(qty * unit_price, 2)
        elif unit_price == 0.0 and total > 0.0 and qty > 0.0:
            unit_price = round(total / qty, 2)

        if total > 0.0 or unit_price > 0.0:
            items.append({
                'description': desc,
                'quantity': qty,
                'unit_price': unit_price,
                'total': total
            })
            end_row_idx = r_idx

    return items, header_row_idx, end_row_idx

def extract_excel_invoice_data(file_path: str, filename: str) -> Dict[str, Any]:
    """
    Comprehensive extraction of invoice data from Excel workbook.
    Returns normalized dictionary compatible with SecureDoc AI schema.
    """
    read_res = validate_and_read_excel(file_path)
    if not read_res['success']:
        return {
            'is_supported': False,
            'status': 'FAILED',
            'doc_type': 'unsupported',
            'message': read_res['error']
        }

    sheets_data = read_res['sheets']
    cls = score_invoice_likelihood(sheets_data, filename)
    if not cls['is_supported']:
        return {
            'is_supported': False,
            'status': 'UNSUPPORTED',
            'doc_type': cls['doc_type'],
            'message': cls['reason'],
            'details': cls.get('details')
        }

    # Extract primary invoice sheet
    sheet_name, grid = find_primary_invoice_sheet(sheets_data)
    items, header_row_idx, end_row_idx = parse_line_items_from_grid(grid)

    # Clean flat text lines for metadata lookup
    flat_lines: List[str] = []
    for r in grid:
        l = ' | '.join(clean_cell_str(c) for c in r if c is not None and str(c).strip())
        if l: flat_lines.append(l)

    full_text = '\n'.join(flat_lines)

    # 1. Invoice Number
    invoice_number = ''
    # Check cell-by-cell first for exact labeled cell
    for r in grid[:25]:
        for c_idx, cell in enumerate(r):
            raw_val = clean_cell_str(cell)
            cs = raw_val.lower().strip()
            if any(k == cs or cs.startswith(k) for k in ['invoice no', 'invoice #', 'invoice number', 'inv no', 'inv #', 'bill no', 'bill number']):
                # Check if value is in same cell e.g. "Invoice Number: INV-2026-001"
                m_same = re.search(r'(?:invoice\s*(?:no\.?|number|#)?|inv\s*(?:no\.?|#)?|bill\s*no\.?)\s*[:#|–-]\s*([A-Za-z0-9/_-]{3,})', raw_val, re.I)
                if m_same and m_same.group(1).lower() not in ('date', 'due', 'number', 'no'):
                    invoice_number = m_same.group(1).strip()
                    break
                # Check next column
                if c_idx + 1 < len(r) and r[c_idx + 1] is not None:
                    val = clean_cell_str(r[c_idx + 1])
                    if val and len(val) >= 2 and val.lower() not in ('date', 'due', 'number', 'no'):
                        invoice_number = val
                        break
        if invoice_number:
            break

    if not invoice_number:
        m = re.search(r'invoice\s*(?:no\.?|number|#)\s*[:#|–-]?\s*([A-Za-z0-9/_-]{3,})', full_text, re.I)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in ('date', 'details', 'number', 'no'):
                invoice_number = candidate

    # 2. Dates
    invoice_date = ''
    due_date = ''
    for r in grid:
        for c_idx, cell in enumerate(r):
            cs = clean_cell_str(cell).lower()
            if any(k in cs for k in ['invoice date', 'date of invoice', 'issue date', 'bill date']):
                if c_idx + 1 < len(r) and r[c_idx + 1] is not None:
                    d_str = clean_cell_str(r[c_idx + 1])
                    if d_str: invoice_date = d_str
            elif any(k in cs for k in ['due date', 'payment due']):
                if c_idx + 1 < len(r) and r[c_idx + 1] is not None:
                    d_str = clean_cell_str(r[c_idx + 1])
                    if d_str: due_date = d_str

    if not invoice_date:
        m = re.search(r'(?:date)\s*[:#|–-]?\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})', full_text, re.I)
        if m: invoice_date = m.group(1)
    if not invoice_date:
        invoice_date = datetime.date.today().isoformat()

    # 3. Vendor Name & Details
    vendor_name = ''
    vendor_email = ''
    vendor_phone = ''

    # Check email / phone regex in sheet
    m_email = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', full_text)
    if m_email: vendor_email = m_email.group(0)

    m_phone = re.search(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}', full_text)
    if m_phone: vendor_phone = m_phone.group(0)

    # Check vendor label
    for r in grid[:15]:
        for c_idx, cell in enumerate(r):
            cs = clean_cell_str(cell).lower()
            if any(k in cs for k in ['vendor', 'supplier', 'seller', 'from:']):
                if c_idx + 1 < len(r) and r[c_idx + 1] is not None:
                    v = clean_cell_str(r[c_idx + 1])
                    if v and len(v) > 2:
                        vendor_name = v
                        break

    if not vendor_name:
        # Top-left cell often contains company name
        for r in grid[:4]:
            first_val = clean_cell_str(r[0]) if r and r[0] is not None else ''
            if first_val and len(first_val) > 2 and not any(k in first_val.lower() for k in ['invoice', 'bill to', 'date', 'page']):
                vendor_name = first_val
                break

    if not vendor_name:
        vendor_name = 'Unknown Vendor'

    # 4. Customer Name (Bill To)
    customer_name = ''
    for r in grid[:15]:
        for c_idx, cell in enumerate(r):
            cs = clean_cell_str(cell).lower()
            if any(k in cs for k in ['bill to', 'billed to', 'customer', 'client:']):
                if c_idx + 1 < len(r) and r[c_idx + 1] is not None:
                    c_val = clean_cell_str(r[c_idx + 1])
                    if c_val: customer_name = c_val; break
                # Sometimes customer name is directly on next row
                row_idx = grid.index(r)
                if row_idx + 1 < len(grid) and grid[row_idx + 1][c_idx] is not None:
                    next_val = clean_cell_str(grid[row_idx + 1][c_idx])
                    if next_val and not customer_name:
                        customer_name = next_val; break

    # 5. PO Number
    po_number = ''
    m_po = re.search(r'(?:po\s*(?:number|no|#)?|purchase\s*order)\s*[:#|–-]?\s*([A-Za-z0-9/_-]{2,})', full_text, re.I)
    if m_po: po_number = m_po.group(1).strip()

    # 6. Currency
    currency = 'BDT'
    if re.search(r'৳|\bBDT\b', full_text, re.I):
        currency = 'BDT'
    elif re.search(r'\$|\bUSD\b', full_text, re.I):
        currency = 'USD'
    elif re.search(r'€|\bEUR\b', full_text, re.I):
        currency = 'EUR'
    elif re.search(r'£|\bGBP\b', full_text, re.I):
        currency = 'GBP'

    # 7. Financial Totals (Subtotal, Discount, Tax, Shipping, Total)
    subtotal = 0.0
    discount = 0.0
    tax = 0.0
    shipping = 0.0
    total = 0.0

    # Scan bottom section or rightmost cells for labels
    for r in grid:
        for c_idx, cell in enumerate(r):
            cs = clean_cell_str(cell).lower()
            if any(k in cs for k in ['subtotal', 'sub total', 'net amount']):
                val = parse_number(r[c_idx + 1] if c_idx + 1 < len(r) else None)
                if val is not None: subtotal = val
            elif any(k in cs for k in ['discount', 'rebate']):
                val = parse_number(r[c_idx + 1] if c_idx + 1 < len(r) else None)
                if val is not None: discount = val
            elif any(k in cs for k in ['tax', 'vat', 'gst']) and not any(k in cs for k in ['tax invoice', 'vat reg', 'tax id']):
                val = parse_number(r[c_idx + 1] if c_idx + 1 < len(r) else None)
                if val is not None: tax = val
            elif any(k in cs for k in ['shipping', 'freight', 'delivery']):
                val = parse_number(r[c_idx + 1] if c_idx + 1 < len(r) else None)
                if val is not None: shipping = val
            elif any(k in cs for k in ['grand total', 'total amount', 'total due', 'amount due', 'balance due', 'total:']):
                val = parse_number(r[c_idx + 1] if c_idx + 1 < len(r) else None)
                if val is not None: total = val

    # If subtotal missing from cell, compute from line items
    if items and subtotal == 0.0:
        subtotal = round(sum(i['total'] for i in items), 2)

    # If total missing, calculate standard formula
    if total == 0.0 and subtotal > 0.0:
        total = round(subtotal - discount + tax + shipping, 2)

    confidence = 95.0 if (vendor_name and total > 0.0 and invoice_number) else 80.0

    return {
        'is_supported': True,
        'status': 'PROCESSED',
        'document_type': 'invoice',
        'sheet_name': sheet_name,
        'invoice_number': invoice_number or filename.rsplit('.', 1)[0],
        'vendor_name': vendor_name,
        'vendor_email': vendor_email,
        'vendor_phone': vendor_phone,
        'customer_name': customer_name,
        'invoice_date': invoice_date,
        'due_date': due_date,
        'purchase_order': po_number,
        'currency': currency,
        'subtotal': subtotal,
        'discount': discount,
        'tax': tax,
        'shipping': shipping,
        'total': total,
        'items': items,
        'confidence': confidence,
        'full_text': full_text
    }
