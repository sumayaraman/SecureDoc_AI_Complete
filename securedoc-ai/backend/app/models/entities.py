from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Numeric, Text, Integer, Boolean, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__='users'
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String(120))
    email: Mapped[str]=mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class Organization(Base):
    __tablename__='organizations'
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String(200))
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class OrganizationMember(Base):
    __tablename__='organization_members'
    __table_args__=(UniqueConstraint('organization_id','user_id',name='uq_org_user'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    organization_id: Mapped[int]=mapped_column(ForeignKey('organizations.id'),index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    role: Mapped[str]=mapped_column(String(20),default='owner')

class Document(Base):
    __tablename__='documents'
    id: Mapped[int]=mapped_column(primary_key=True)
    organization_id: Mapped[int]=mapped_column(ForeignKey('organizations.id'),index=True)
    filename: Mapped[str]=mapped_column(String(255))
    mime_type: Mapped[str]=mapped_column(String(120))
    storage_key: Mapped[str]=mapped_column(String(500),unique=True)
    file_hash: Mapped[str]=mapped_column(String(64),index=True)
    status: Mapped[str]=mapped_column(String(40),default='UPLOADED')
    extracted_text: Mapped[str|None]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class Vendor(Base):
    __tablename__='vendors'
    id: Mapped[int]=mapped_column(primary_key=True)
    organization_id: Mapped[int]=mapped_column(ForeignKey('organizations.id'),index=True)
    name: Mapped[str]=mapped_column(String(255))

class Invoice(Base):
    __tablename__='invoices'
    id: Mapped[int]=mapped_column(primary_key=True)
    organization_id: Mapped[int]=mapped_column(ForeignKey('organizations.id'),index=True)
    document_id: Mapped[int]=mapped_column(ForeignKey('documents.id'),index=True)
    vendor_id: Mapped[int|None]=mapped_column(ForeignKey('vendors.id'),nullable=True)
    invoice_number: Mapped[str|None]=mapped_column(String(120),index=True)
    vendor_name: Mapped[str|None]=mapped_column(String(200),index=True)
    invoice_date: Mapped[str|None]=mapped_column(String(30))
    due_date: Mapped[str|None]=mapped_column(String(30))
    subtotal: Mapped[float|None]=mapped_column(Numeric(14,2))
    discount: Mapped[float|None]=mapped_column(Numeric(14,2))
    tax: Mapped[float|None]=mapped_column(Numeric(14,2))
    total: Mapped[float|None]=mapped_column(Numeric(14,2))
    currency: Mapped[str|None]=mapped_column(String(8))
    status: Mapped[str]=mapped_column(String(40),default='NEEDS_REVIEW',index=True)
    confidence: Mapped[float]=mapped_column(Numeric(5,2),default=0)
    validation_difference: Mapped[float]=mapped_column(Numeric(14,2),default=0)
    duplicate: Mapped[bool]=mapped_column(Boolean,default=False)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class InvoiceItem(Base):
    __tablename__='invoice_items'
    id: Mapped[int]=mapped_column(primary_key=True)
    invoice_id: Mapped[int]=mapped_column(ForeignKey('invoices.id',ondelete='CASCADE'),index=True)
    description: Mapped[str]=mapped_column(String(500))
    quantity: Mapped[float]=mapped_column(Numeric(14,3),default=1)
    unit_price: Mapped[float]=mapped_column(Numeric(14,2),default=0)
    total: Mapped[float]=mapped_column(Numeric(14,2),default=0)

class ProcessingJob(Base):
    __tablename__='processing_jobs'
    id: Mapped[int]=mapped_column(primary_key=True)
    document_id: Mapped[int]=mapped_column(ForeignKey('documents.id'),index=True)
    status: Mapped[str]=mapped_column(String(40),default='QUEUED')
    stage: Mapped[str]=mapped_column(String(60),default='UPLOADED')
    error_message: Mapped[str|None]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    completed_at: Mapped[datetime|None]=mapped_column(DateTime)

class ValidationResult(Base):
    __tablename__='validation_results'
    id: Mapped[int]=mapped_column(primary_key=True)
    invoice_id: Mapped[int]=mapped_column(ForeignKey('invoices.id'),index=True)
    valid: Mapped[bool]=mapped_column(Boolean,default=False)
    difference: Mapped[float]=mapped_column(Numeric(14,2),default=0)
    message: Mapped[str]=mapped_column(Text)

class AuditLog(Base):
    __tablename__='audit_logs'
    id: Mapped[int]=mapped_column(primary_key=True)
    organization_id: Mapped[int]=mapped_column(ForeignKey('organizations.id'),index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    action: Mapped[str]=mapped_column(String(80))
    resource: Mapped[str]=mapped_column(String(160))
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class Notification(Base):
    __tablename__='notifications'
    id: Mapped[int]=mapped_column(primary_key=True)
    organization_id: Mapped[int]=mapped_column(ForeignKey('organizations.id'),index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    title: Mapped[str]=mapped_column(String(200))
    message: Mapped[str]=mapped_column(Text)
    read: Mapped[bool]=mapped_column(Boolean,default=False)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class AIQuery(Base):
    __tablename__='ai_queries'
    id: Mapped[int]=mapped_column(primary_key=True)
    organization_id: Mapped[int]=mapped_column(ForeignKey('organizations.id'),index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    question: Mapped[str]=mapped_column(Text)
    answer: Mapped[str]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
