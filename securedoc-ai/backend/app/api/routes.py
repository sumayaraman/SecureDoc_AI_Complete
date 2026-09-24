import os, hashlib, csv, io, re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from app.database.db import get_db
from app.models.entities import *
from app.security.auth import hash_password, verify_password, make_token, current_context, require_role
from app.services.ai import AIService
from app.services.extractor import extract_text
from app.services.validation import validate_invoice

router=APIRouter(); STORAGE=Path(os.getenv('STORAGE_DIR','./storage')).resolve(); STORAGE.mkdir(parents=True,exist_ok=True)
ALLOWED={'application/pdf','image/jpeg','image/png'}; MAX=10*1024*1024
class Register(BaseModel): name:str; email:EmailStr; password:str; organization_name:str='My Organization'
class Login(BaseModel): email:EmailStr; password:str
class AssistantQuery(BaseModel): question:str
class InvoiceUpdate(BaseModel): vendor_name:str|None=None; invoice_number:str|None=None; invoice_date:str|None=None; due_date:str|None=None; subtotal:float|None=None; discount:float|None=None; tax:float|None=None; total:float|None=None; currency:str|None=None; status:str|None=None
class ReviewBody(BaseModel): approved:bool=True


def audit(db,org,user,action,resource): db.add(AuditLog(organization_id=org,user_id=user,action=action,resource=resource)); db.commit()
def serialize_invoice(i,doc=None): return {'id':i.id,'document_id':i.document_id,'invoice_number':i.invoice_number,'vendor':i.vendor_name,'date':i.invoice_date,'due_date':i.due_date,'subtotal':float(i.subtotal or 0),'discount':float(i.discount or 0),'tax':float(i.tax or 0),'amount':float(i.total or 0),'currency':i.currency,'status':i.status,'confidence':float(i.confidence or 0),'duplicate':i.duplicate,'filename':doc.filename if doc else None,'created_at':i.created_at.isoformat()}
def safe_path(key):
    p=(STORAGE/key).resolve()
    if STORAGE not in p.parents: raise HTTPException(400,'Invalid storage key')
    return p

def validate_result_payload(result):
    if not isinstance(result,dict): raise ValueError('AI returned invalid data')
    for k in ['subtotal','discount','tax','total','confidence']:
        try: result[k]=float(result.get(k) or 0)
        except Exception: result[k]=0.0
    result['items']=result.get('items') if isinstance(result.get('items'),list) else []
    return result

@router.post('/auth/register')
def register(body:Register,db:Session=Depends(get_db)):
    if len(body.password)<8: raise HTTPException(400,'Password must be at least 8 characters')
    if db.query(User).filter_by(email=body.email.lower()).first(): raise HTTPException(409,'Email already registered')
    u=User(name=body.name.strip(),email=body.email.lower(),password_hash=hash_password(body.password)); db.add(u); db.flush(); o=Organization(name=body.organization_name.strip() or 'My Organization'); db.add(o); db.flush(); db.add(OrganizationMember(organization_id=o.id,user_id=u.id,role='owner')); db.commit(); return {'token':make_token(u.id),'user':{'id':u.id,'name':u.name,'email':u.email},'organization':{'id':o.id,'name':o.name},'role':'owner'}

@router.post('/auth/login')
def login(body:Login,db:Session=Depends(get_db)):
    u=db.query(User).filter_by(email=body.email.lower()).first()
    if not u or not verify_password(body.password,u.password_hash): raise HTTPException(401,'Invalid email or password')
    m=db.query(OrganizationMember).filter_by(user_id=u.id).first(); o=db.get(Organization,m.organization_id); return {'token':make_token(u.id),'user':{'id':u.id,'name':u.name,'email':u.email},'organization':{'id':o.id,'name':o.name},'role':m.role}

@router.get('/auth/me')
def me(authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); o=db.get(Organization,m.organization_id); return {'user':{'id':u.id,'name':u.name,'email':u.email},'organization':{'id':o.id,'name':o.name},'role':m.role}

@router.post('/documents/upload')
async def upload(file:UploadFile=File(...),authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); require_role(m,'owner','admin','member')
    if file.content_type not in ALLOWED: raise HTTPException(400,'Only PDF, JPG and PNG files are supported')
    data=await file.read()
    if len(data)>MAX: raise HTTPException(413,'Maximum file size is 10 MB')
    digest=hashlib.sha256(data).hexdigest(); existing=db.query(Document).filter_by(organization_id=m.organization_id,file_hash=digest).first()
    if existing: raise HTTPException(409,'This file already exists in the workspace')
    suffix=Path(file.filename or 'document').suffix.lower(); key=f'{m.organization_id}/{digest}{suffix}'; path=safe_path(key); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
    doc=Document(organization_id=m.organization_id,filename=file.filename or 'document',mime_type=file.content_type,storage_key=key,file_hash=digest,status='PROCESSING'); db.add(doc); db.flush(); job=ProcessingJob(document_id=doc.id,status='PROCESSING',stage='TEXT_EXTRACTION'); db.add(job); db.commit()
    try:
        text=extract_text(str(path),file.content_type); doc.extracted_text=text[:200000]; job.stage='AI_EXTRACTION'
        result=validate_result_payload(await AIService().extract_invoice(text,file.filename or 'invoice'))
        job.stage='VALIDATION'
        validation=validate_invoice(result.get('items',[]),Decimal(str(result.get('subtotal',0))),Decimal(str(result.get('discount',0))),Decimal(str(result.get('tax',0))),Decimal(str(result.get('total',0))))
        inv=Invoice(organization_id=m.organization_id,document_id=doc.id,invoice_number=result.get('invoice_number'),vendor_name=result.get('vendor_name'),invoice_date=result.get('invoice_date'),due_date=result.get('due_date'),subtotal=result.get('subtotal',0),discount=result.get('discount',0),tax=result.get('tax',0),total=result.get('total',0),currency=result.get('currency','BDT'),confidence=result.get('confidence',0),status='PROCESSED'); db.add(inv); db.flush()
        for item in result['items']:
            try: db.add(InvoiceItem(invoice_id=inv.id,description=str(item.get('description','Unknown item'))[:500],quantity=float(item.get('quantity',0) or 0),unit_price=float(item.get('unit_price',0) or 0),total=float(item.get('total',0) or 0)))
            except Exception: pass
        vr=ValidationResult(invoice_id=inv.id,valid=validation['valid'],difference=float(validation['difference']),message='Validated successfully' if validation['valid'] else 'Calculation mismatch requires review'); db.add(vr); inv.validation_difference=float(validation['difference'])
        if not text.strip(): inv.status='NEEDS_REVIEW'
        if not validation['valid'] or inv.confidence<85: inv.status='NEEDS_REVIEW'
        dup=db.query(Invoice).filter(Invoice.organization_id==m.organization_id,Invoice.invoice_number==inv.invoice_number,Invoice.id!=inv.id).first()
        if dup: inv.duplicate=True; inv.status='DUPLICATE'
        doc.status=inv.status; job.stage='COMPLETED'; job.status='COMPLETED'; job.completed_at=datetime.utcnow(); db.add(Notification(organization_id=m.organization_id,user_id=u.id,title='Invoice processed',message=f'{doc.filename} is ready for review.')); db.commit(); audit(db,m.organization_id,u.id,'UPLOAD_PROCESS','invoice:'+str(inv.id)); return serialize_invoice(inv,doc)
    except Exception as e:
        db.rollback(); doc=db.get(Document,doc.id); job=db.get(ProcessingJob,job.id); doc.status='FAILED'; job.status='FAILED'; job.stage='FAILED'; job.error_message=str(e)[:500]; db.commit(); raise HTTPException(500,'Document processing failed')

@router.get('/documents')
def documents(q:str|None=None,status:str|None=None,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); query=db.query(Document).filter_by(organization_id=m.organization_id)
    if q: query=query.filter(Document.filename.ilike(f'%{q}%'))
    if status: query=query.filter(Document.status==status)
    docs=query.order_by(Document.created_at.desc()).all(); return {'items':[{'id':d.id,'filename':d.filename,'status':d.status,'mime_type':d.mime_type,'created_at':d.created_at.isoformat()} for d in docs]}

@router.get('/documents/{document_id}/download')
def download_document(document_id:int,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); d=db.query(Document).filter_by(id=document_id,organization_id=m.organization_id).first()
    if not d: raise HTTPException(404,'Document not found')
    p=safe_path(d.storage_key)
    if not p.exists(): raise HTTPException(404,'Stored document not found')
    return FileResponse(p,media_type=d.mime_type,filename=d.filename)

@router.get('/invoices')
def invoices(q:str|None=None,status:str|None=None,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); query=db.query(Invoice).filter_by(organization_id=m.organization_id)
    if q: query=query.filter(or_(Invoice.invoice_number.ilike(f'%{q}%'),Invoice.vendor_name.ilike(f'%{q}%')))
    if status: query=query.filter(Invoice.status==status)
    rows=query.order_by(Invoice.created_at.desc()).all(); return {'items':[serialize_invoice(i,db.get(Document,i.document_id)) for i in rows]}

@router.get('/invoices/{invoice_id}')
def invoice_detail(invoice_id:int,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); i=db.query(Invoice).filter_by(id=invoice_id,organization_id=m.organization_id).first()
    if not i: raise HTTPException(404,'Invoice not found')
    d=db.get(Document,i.document_id); v=db.query(ValidationResult).filter_by(invoice_id=i.id).first(); items=db.query(InvoiceItem).filter_by(invoice_id=i.id).all(); job=db.query(ProcessingJob).filter_by(document_id=i.document_id).order_by(ProcessingJob.created_at.desc()).first()
    return {**serialize_invoice(i,d),'validation':{'valid':v.valid,'difference':float(v.difference),'message':v.message} if v else None,'items':[{'id':x.id,'description':x.description,'quantity':float(x.quantity),'unit_price':float(x.unit_price),'total':float(x.total)} for x in items],'processing':{'status':job.status,'stage':job.stage,'error':job.error_message} if job else None}

@router.patch('/invoices/{invoice_id}')
def update_invoice(invoice_id:int,body:InvoiceUpdate,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); require_role(m,'owner','admin','member'); i=db.query(Invoice).filter_by(id=invoice_id,organization_id=m.organization_id).first()
    if not i: raise HTTPException(404,'Invoice not found')
    for k,v in body.model_dump(exclude_none=True).items(): setattr(i,k,v)
    if i.status=='PROCESSED' and abs(float(i.validation_difference or 0))>0.01:i.status='NEEDS_REVIEW'
    db.commit(); audit(db,m.organization_id,u.id,'UPDATE','invoice:'+str(i.id)); return serialize_invoice(i,db.get(Document,i.document_id))

@router.post('/invoices/{invoice_id}/review')
def review_invoice(invoice_id:int,body:ReviewBody,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); require_role(m,'owner','admin','member'); i=db.query(Invoice).filter_by(id=invoice_id,organization_id=m.organization_id).first()
    if not i: raise HTTPException(404,'Invoice not found')
    if i.duplicate: raise HTTPException(400,'Duplicate invoices must be resolved before approval')
    i.status='PROCESSED' if body.approved else 'NEEDS_REVIEW'; d=db.get(Document,i.document_id); d.status=i.status; db.commit(); audit(db,m.organization_id,u.id,'REVIEW_APPROVED' if body.approved else 'REVIEW_REOPENED','invoice:'+str(i.id)); return serialize_invoice(i,d)

@router.delete('/invoices/{invoice_id}')
def delete_invoice(invoice_id:int,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); require_role(m,'owner','admin'); i=db.query(Invoice).filter_by(id=invoice_id,organization_id=m.organization_id).first()
    if not i: raise HTTPException(404,'Invoice not found')
    d=db.get(Document,i.document_id); p=safe_path(d.storage_key)
    db.delete(i); db.delete(d); db.commit()
    if p.exists(): p.unlink()
    audit(db,m.organization_id,u.id,'DELETE','invoice:'+str(invoice_id)); return {'ok':True}

@router.get('/analytics/overview')
def analytics(authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); q=db.query(Invoice).filter_by(organization_id=m.organization_id); total=float(q.with_entities(func.coalesce(func.sum(Invoice.total),0)).scalar() or 0); count=q.count(); vendors=q.with_entities(func.count(func.distinct(Invoice.vendor_name))).scalar() or 0; pending=q.filter(Invoice.status.in_(['NEEDS_REVIEW','DUPLICATE'])).count(); return {'total_documents':db.query(Document).filter_by(organization_id=m.organization_id).count(),'total_spending':total,'invoice_count':count,'vendors':int(vendors),'pending_review':pending}

@router.get('/analytics/spending')
def spending(authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); rows=db.query(Invoice.invoice_date,func.sum(Invoice.total)).filter_by(organization_id=m.organization_id).group_by(Invoice.invoice_date).order_by(Invoice.invoice_date).all(); vendors=db.query(Invoice.vendor_name,func.sum(Invoice.total)).filter_by(organization_id=m.organization_id).group_by(Invoice.vendor_name).order_by(func.sum(Invoice.total).desc()).limit(10).all(); return {'by_date':[{'date':x[0],'amount':float(x[1] or 0)} for x in rows],'by_vendor':[{'vendor':x[0] or 'Unknown','amount':float(x[1] or 0)} for x in vendors]}

@router.get('/notifications')
def notifications(authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); return {'items':[{'id':n.id,'title':n.title,'message':n.message,'read':n.read,'created_at':n.created_at.isoformat()} for n in db.query(Notification).filter_by(organization_id=m.organization_id,user_id=u.id).order_by(Notification.created_at.desc()).limit(20).all()]}
@router.post('/notifications/{notification_id}/read')
def notification_read(notification_id:int,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); n=db.query(Notification).filter_by(id=notification_id,organization_id=m.organization_id,user_id=u.id).first()
    if not n: raise HTTPException(404,'Notification not found')
    n.read=True; db.commit(); return {'ok':True}

@router.get('/audit-logs')
def audit_logs(authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); return {'items':[{'action':x.action,'resource':x.resource,'created_at':x.created_at.isoformat()} for x in db.query(AuditLog).filter_by(organization_id=m.organization_id).order_by(AuditLog.created_at.desc()).limit(100).all()]}

@router.post('/assistant/query')
def assistant(body:AssistantQuery,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); q=body.question.lower().strip(); invq=db.query(Invoice).filter_by(organization_id=m.organization_id); sources=[]
    if 'pending' in q or 'review' in q:
        query=invq.filter(Invoice.status.in_(['NEEDS_REVIEW','DUPLICATE'])); answer=f'There are {query.count()} invoices needing review.'; sources=[x.id for x in query.limit(10).all()]
    elif 'top' in q and 'vendor' in q:
        rows=db.query(Invoice.vendor_name,func.sum(Invoice.total).label('amount')).filter_by(organization_id=m.organization_id).group_by(Invoice.vendor_name).order_by(func.sum(Invoice.total).desc()).limit(5).all(); answer='Top vendors by spending: '+', '.join(f'{x[0] or "Unknown"} — {float(x[1] or 0):,.2f}' for x in rows) if rows else 'There is not enough invoice data yet.'
    elif any(w in q for w in ['how much','spend','spent','total spending']):
        vendor=None
        for i in invq.with_entities(Invoice.vendor_name).distinct().all():
            if i[0] and i[0].lower() in q: vendor=i[0]; break
        query=invq.filter(Invoice.vendor_name==vendor) if vendor else invq; amount=float(query.with_entities(func.coalesce(func.sum(Invoice.total),0)).scalar() or 0); answer=f'Total spending{f" with {vendor}" if vendor else ""} is {amount:,.2f} BDT.'; sources=[x.id for x in query.order_by(Invoice.created_at.desc()).limit(10).all()]
    elif 'count' in q or 'how many invoice' in q:
        answer=f'There are {invq.count()} invoices in your workspace.'; sources=[x.id for x in invq.order_by(Invoice.created_at.desc()).limit(10).all()]
    else: answer='I can answer spending, vendor, invoice-count and review-status questions using your stored invoice data.'
    db.add(AIQuery(organization_id=m.organization_id,user_id=u.id,question=body.question,answer=answer)); db.commit(); return {'answer':answer,'sources':sources}


def rows_for_org(db,m): return db.query(Invoice).filter_by(organization_id=m.organization_id).order_by(Invoice.created_at.desc()).all()
@router.get('/reports/export.csv')
def export_csv(authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); out=io.StringIO(); w=csv.writer(out); w.writerow(['Invoice Number','Vendor','Date','Due Date','Subtotal','Discount','Tax','Total','Currency','Status','Confidence'])
    for i in rows_for_org(db,m): w.writerow([i.invoice_number,i.vendor_name,i.invoice_date,i.due_date,i.subtotal,i.discount,i.tax,i.total,i.currency,i.status,i.confidence])
    return StreamingResponse(iter([out.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=securedoc-invoices.csv'})
@router.get('/reports/export.xlsx')
def export_xlsx(authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); from openpyxl import Workbook; wb=Workbook(); ws=wb.active; ws.title='Invoices'; ws.append(['Invoice Number','Vendor','Date','Due Date','Subtotal','Discount','Tax','Total','Currency','Status','Confidence'])
    for i in rows_for_org(db,m): ws.append([i.invoice_number,i.vendor_name,i.invoice_date,i.due_date,float(i.subtotal or 0),float(i.discount or 0),float(i.tax or 0),float(i.total or 0),i.currency,i.status,float(i.confidence or 0)])
    buf=io.BytesIO(); wb.save(buf); buf.seek(0); return StreamingResponse(buf,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename=securedoc-invoices.xlsx'})
@router.get('/reports/export.pdf')
def export_pdf(authorization:str|None=Header(None),db:Session=Depends(get_db)):
    u,m=current_context(db,authorization); from reportlab.lib.pagesizes import A4; from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle; from reportlab.lib import colors; from reportlab.lib.styles import getSampleStyleSheet
    buf=io.BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=30,leftMargin=30,topMargin=30,bottomMargin=30); styles=getSampleStyleSheet(); data=[['Invoice','Vendor','Date','Total','Status']]
    for i in rows_for_org(db,m): data.append([i.invoice_number or '-',i.vendor_name or 'Unknown',i.invoice_date or '-',f'{float(i.total or 0):,.2f} {i.currency or ""}',i.status])
    story=[Paragraph(f'{db.get(Organization,m.organization_id).name} — Invoice Report',styles['Title']),Spacer(1,12),Paragraph(f'Generated {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}',styles['Normal']),Spacer(1,12),Table(data,repeatRows=1)]
    story[-1].setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eef2ff')),('GRID',(0,0),(-1,-1),0.4,colors.grey),('FONTSIZE',(0,0),(-1,-1),8),('VALIGN',(0,0),(-1,-1),'TOP')]))
    doc.build(story); buf.seek(0); return StreamingResponse(buf,media_type='application/pdf',headers={'Content-Disposition':'attachment; filename=securedoc-invoice-report.pdf'})
