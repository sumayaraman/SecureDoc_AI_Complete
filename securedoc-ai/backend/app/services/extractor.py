import re
from datetime import datetime

def extract_text(path:str,mime:str)->str:
    if mime=='application/pdf':
        try:
            import fitz
            doc=fitz.open(path); text='\n'.join(page.get_text() for page in doc)
            if text.strip(): return text
            # OCR scanned PDF pages when pytesseract + poppler-like rendering is available.
            return ocr_image_document(path, is_pdf=True)
        except Exception: return ''
    if mime.startswith('image/'):
        return ocr_image_document(path, is_pdf=False)
    return ''

def ocr_image_document(path:str,is_pdf:bool=False)->str:
    try:
        import pytesseract
        from PIL import Image
        if is_pdf:
            import fitz
            doc=fitz.open(path); chunks=[]
            for page in doc:
                pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
                img=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
                chunks.append(pytesseract.image_to_string(img))
            return '\n'.join(chunks)
        return pytesseract.image_to_string(Image.open(path))
    except Exception:
        return ''

def money(text:str, labels:list[str]):
    for label in labels:
        m=re.search(rf'{re.escape(label)}\s*[:#-]?\s*(?:৳|BDT|USD|\$)?\s*([0-9][0-9,]*(?:\.\d+)?)',text,re.I)
        if m:return float(m.group(1).replace(',',''))
    return 0.0

def parse_invoice(text:str,filename:str)->dict:
    clean=' '.join(text.split()); lines=[x.strip() for x in text.splitlines() if x.strip()]
    vendor=''; m=re.search(r'(?:vendor|supplier|seller|from)\s*[:#-]\s*([A-Za-z0-9 &.,_-]{2,120})',clean,re.I)
    if m: vendor=m.group(1).strip()
    if not vendor: vendor=lines[0][:120] if lines else 'Unknown Vendor'
    num=''; m=re.search(r'(?:invoice\s*(?:no|number|#)?)\s*[:#-]?\s*([A-Z0-9][A-Z0-9/_-]{2,})',clean,re.I)
    if m:num=m.group(1)
    date=''; m=re.search(r'(?:invoice\s*date|date)\s*[:#-]?\s*(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4})',clean,re.I)
    if m:date=m.group(1)
    currency='BDT' if re.search(r'৳|\bBDT\b',clean,re.I) else 'USD' if re.search(r'\$|\bUSD\b',clean,re.I) else 'BDT'
    subtotal=money(clean,['subtotal','sub total']); discount=money(clean,['discount']); tax=money(clean,['tax','vat']); total=money(clean,['grand total','total amount','total due','total'])
    if total==0 and subtotal: total=subtotal-discount+tax
    return {'vendor_name':vendor,'invoice_number':num or filename.rsplit('.',1)[0],'invoice_date':date or datetime.utcnow().date().isoformat(),'due_date':'','subtotal':subtotal,'discount':discount,'tax':tax,'total':total,'currency':currency,'items':[],'confidence':70.0}
