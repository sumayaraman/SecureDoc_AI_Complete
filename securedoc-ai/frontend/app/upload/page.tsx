'use client';

import { useRef, useState, useEffect } from 'react';
import { Shell } from '../../components/shell';
import { Card, Badge } from '../../components/ui';
import { uploadFile, getDocumentStatus } from '../../lib/api';
import {
  UploadCloud,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  FileText,
  Eye,
  ArrowRight,
  RefreshCw,
  Copy,
  FileX,
  ChevronDown,
  ChevronUp,
  FileSpreadsheet,
} from 'lucide-react';
import Link from 'next/link';

interface UploadItem {
  id: string;
  file: File;
  previewUrl: string;
  isPdf: boolean;
  isImage: boolean;
  isExcel: boolean;
  status:
    | 'selected'
    | 'uploading'
    | 'extracting'
    | 'validating'
    | 'completed'
    | 'review_required'
    | 'duplicate'
    | 'unsupported'
    | 'failed';
  stageText: string;
  backendStage?: string;
  error?: string;
  result?: any;
}

export default function Upload() {
  const ref = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [showItemsMap, setShowItemsMap] = useState<Record<string, boolean>>({});

  useEffect(() => {
    return () => {
      // Clean up object URLs on unmount
      items.forEach(i => {
        if (i.previewUrl) URL.revokeObjectURL(i.previewUrl);
      });
    };
  }, [items]);

  function handleFileSelection(files: FileList | null) {
    if (!files || files.length === 0) return;
    const newItems: UploadItem[] = Array.from(files).map((file, idx) => {
      const ext = file.name.toLowerCase();
      const isPdf = file.type === 'application/pdf' || ext.endsWith('.pdf');
      const isImage = file.type.startsWith('image/') || ext.endsWith('.jpg') || ext.endsWith('.jpeg') || ext.endsWith('.png');
      const isExcel =
        ext.endsWith('.xlsx') ||
        ext.endsWith('.xls') ||
        ext.endsWith('.csv') ||
        file.type.includes('spreadsheet') ||
        file.type.includes('excel') ||
        file.type === 'text/csv' ||
        file.type === 'application/csv';
      const previewUrl = URL.createObjectURL(file);
      return {
        id: `${Date.now()}-${idx}-${file.name}`,
        file,
        previewUrl,
        isPdf,
        isImage,
        isExcel,
        status: 'uploading',
        stageText: isExcel ? 'Uploading & parsing spreadsheet...' : 'Uploading & securing document...',
      };
    });

    setItems(prev => [...newItems, ...prev]);

    // Process each newly added file
    newItems.forEach(item => {
      executeUpload(item);
    });
  }

  async function executeUpload(item: UploadItem) {
    const applyFinalResult = (data: any) => {
      const normalizedStatus = String(data.status || '').toUpperCase();
      let targetStatus: UploadItem['status'] = 'completed';

      if (normalizedStatus === 'UNSUPPORTED') {
        targetStatus = 'unsupported';
      } else if (normalizedStatus === 'DUPLICATE' || data.duplicate) {
        targetStatus = 'duplicate';
      } else if (normalizedStatus === 'NEEDS_REVIEW') {
        targetStatus = 'review_required';
      } else if (normalizedStatus === 'FAILED') {
        targetStatus = 'failed';
      } else {
        targetStatus = 'completed';
      }

      setItems(curr =>
        curr.map(i =>
          i.id === item.id
            ? {
                ...i,
                status: targetStatus,
                stageText:
                  targetStatus === 'failed'
                    ? (data.message || data.error || 'Processing failed')
                    : 'Processing completed',
                error: targetStatus === 'failed' ? (data.message || data.error || 'Processing failed') : undefined,
                result: data,
                backendStage: data.stage || 'COMPLETED',
              }
            : i
        )
      );
    };

    try {
      // 1. Send real upload request to backend
      const uploadRes = await uploadFile(item.file);

      const statusUpper = String(uploadRes.status || '').toUpperCase();
      const terminalStatuses = ['PROCESSED', 'NEEDS_REVIEW', 'DUPLICATE', 'UNSUPPORTED', 'FAILED'];

      // If backend responded with terminal state directly (synchronous processing)
      if (terminalStatuses.includes(statusUpper)) {
        applyFinalResult(uploadRes);
        return;
      }

      // 2. Real status polling if document is still processing in background
      const docId = uploadRes.document_id || uploadRes.id;
      if (!docId) {
        applyFinalResult(uploadRes);
        return;
      }

      let attempts = 0;
      const maxAttempts = 60; // 30 seconds polling window
      const pollTimer = setInterval(async () => {
        attempts++;
        try {
          const statusRes = await getDocumentStatus(docId);
          const curStatus = String(statusRes.status || '').toUpperCase();
          const curStage = String(statusRes.stage || '').toUpperCase();

          let stageText = 'Processing document...';
          let derivedStatus: UploadItem['status'] = 'uploading';

          if (curStage === 'READING_WORKBOOK') {
            stageText = 'Reading workbook...';
            derivedStatus = 'uploading';
          } else if (curStage === 'DETECTING_STRUCTURE') {
            stageText = 'Detecting invoice structure...';
            derivedStatus = 'extracting';
          } else if (curStage === 'EXTRACTING_DATA') {
            stageText = 'Extracting line items & invoice fields...';
            derivedStatus = 'extracting';
          } else if (curStage === 'VALIDATING_TOTALS') {
            stageText = 'Validating totals & calculations...';
            derivedStatus = 'validating';
          } else if (curStage === 'CHECKING_DUPLICATES') {
            stageText = 'Checking duplicate records...';
            derivedStatus = 'validating';
          } else if (curStage === 'TEXT_EXTRACTION') {
            stageText = 'Extracting document text & OCR...';
            derivedStatus = 'extracting';
          } else if (curStage === 'DOCUMENT_TYPE_DETECTION') {
            stageText = 'Detecting document type...';
            derivedStatus = 'extracting';
          } else if (curStage === 'AI_EXTRACTION') {
            stageText = 'AI extracting invoice metadata...';
            derivedStatus = 'extracting';
          }

          if (terminalStatuses.includes(curStatus)) {
            clearInterval(pollTimer);
            applyFinalResult(statusRes);
          } else {
            setItems(curr =>
              curr.map(i =>
                i.id === item.id
                  ? {
                      ...i,
                      status: derivedStatus,
                      stageText,
                      backendStage: curStage,
                    }
                  : i
              )
            );
          }
        } catch (pollErr) {
          // Keep polling if an individual poll request drops
        }

        if (attempts >= maxAttempts) {
          clearInterval(pollTimer);
          setItems(curr =>
            curr.map(i =>
              i.id === item.id &&
              (i.status === 'uploading' || i.status === 'extracting' || i.status === 'validating')
                ? {
                    ...i,
                    status: 'failed',
                    stageText: 'Processing timed out',
                    error: 'Document processing took longer than expected. Please try again.',
                  }
                : i
            )
          );
        }
      }, 500);
    } catch (err: any) {
      const errorMessage =
        err?.message || 'Processing failed. If the server is waking up, please wait a moment and try again.';

      setItems(curr =>
        curr.map(i =>
          i.id === item.id
            ? {
                ...i,
                status: 'failed',
                stageText: 'Processing failed',
                error: errorMessage,
              }
            : i
        )
      );
    }
  }

  function handleRetry(item: UploadItem) {
    setItems(curr =>
      curr.map(i =>
        i.id === item.id
          ? {
              ...i,
              status: 'uploading',
              stageText: item.isExcel ? 'Uploading & parsing spreadsheet...' : 'Uploading & securing document...',
              error: undefined,
            }
          : i
      )
    );
    executeUpload(item);
  }

  function toggleLineItems(id: string) {
    setShowItemsMap(prev => ({ ...prev, [id]: !prev[id] }));
  }

  return (
    <Shell>
      <div>
        <p className="text-sm font-medium text-indigo-600">Document intake</p>
        <h1 className="mt-1 text-2xl font-bold">Upload invoices</h1>
        <p className="mt-1 text-sm text-slate-500">
          SecureDoc AI extracts text, performs OCR, detects invoice fields, and verifies calculations automatically.
        </p>
      </div>

      {/* Drag & Drop Upload Zone */}
      <Card
        onDragOver={e => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={e => {
          e.preventDefault();
          setIsDragging(false);
        }}
        onDrop={e => {
          e.preventDefault();
          setIsDragging(false);
          handleFileSelection(e.dataTransfer.files);
        }}
        className={`mt-6 border-2 border-dashed p-10 text-center transition-all duration-200 ${
          isDragging
            ? 'border-indigo-500 bg-indigo-50/70 scale-[1.01]'
            : 'border-slate-200 hover:border-indigo-300 hover:bg-slate-50/50'
        }`}
      >
        <input
          ref={ref}
          type="file"
          multiple
          accept="application/pdf,image/jpeg,image/png,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/csv,application/csv,.xlsx,.xls,.csv"
          className="hidden"
          onChange={e => {
            handleFileSelection(e.target.files);
            e.target.value = '';
          }}
          aria-label="Upload invoice documents"
        />

        <div
          className={`mx-auto grid h-16 w-16 place-items-center rounded-2xl transition-transform duration-200 ${
            isDragging ? 'bg-indigo-600 text-white scale-110' : 'bg-indigo-50 text-indigo-600'
          }`}
        >
          <UploadCloud size={32} />
        </div>

        <p className="mt-4 font-bold text-slate-800 text-base">
          {isDragging ? 'Release to upload invoices' : 'Drop invoices here or browse'}
        </p>
        <p className="mt-1 text-sm text-slate-500">Supports PDF, JPG, PNG, Excel (.xlsx, .xls) and CSV files up to 10 MB</p>

        <button
          onClick={() => ref.current?.click()}
          className="mt-5 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 active:scale-95 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
        >
          Choose files
        </button>
      </Card>

      {/* Uploaded Documents List */}
      {items.length > 0 && (
        <div className="mt-8 space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-slate-800">
              {items.some(i => i.status === 'uploading' || i.status === 'extracting' || i.status === 'validating')
                ? `Processing Queue (${items.length} ${items.length === 1 ? 'document' : 'documents'})`
                : `Uploaded Documents (${items.length} ${items.length === 1 ? 'document' : 'documents'})`}
            </h2>
            <button
              onClick={() => ref.current?.click()}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-800"
            >
              + Upload more
            </button>
          </div>

          {items.map(item => {
            const isProcessing =
              item.status === 'uploading' ||
              item.status === 'extracting' ||
              item.status === 'validating';

            return (
              <Card
                key={item.id}
                className="overflow-hidden border border-slate-200 shadow-sm animate-pop-in"
              >
                <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] divide-y lg:divide-y-0 lg:divide-x divide-slate-100">
                  {/* Left Column: Document Preview */}
                  <div className="p-5 bg-slate-50/60 flex flex-col justify-between">
                    <div>
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 overflow-hidden">
                          {item.isExcel ? (
                            <FileSpreadsheet size={18} className="text-emerald-600 shrink-0" />
                          ) : (
                            <FileText size={18} className="text-indigo-600 shrink-0" />
                          )}
                          <p className="text-sm font-semibold text-slate-800 truncate" title={item.file.name}>
                            {item.file.name}
                          </p>
                        </div>
                      </div>
                      <p className="text-xs text-slate-400 mt-1">
                        {(item.file.size / 1024).toFixed(0)} KB •{' '}
                        {item.isPdf
                          ? 'PDF'
                          : item.isImage
                          ? 'Image'
                          : item.isExcel
                          ? item.file.name.toLowerCase().endsWith('.csv')
                            ? 'CSV'
                            : 'Excel'
                          : 'Document'}
                      </p>

                      {/* Visual Preview */}
                      <div className="mt-4">
                        {item.isImage ? (
                          <div className="h-48 w-full rounded-xl border border-slate-200 bg-white p-1 overflow-hidden flex items-center justify-center">
                            <img
                              src={item.previewUrl}
                              alt={item.file.name}
                              className="max-h-full max-w-full object-contain"
                            />
                          </div>
                        ) : item.isExcel ? (
                          <div className="h-48 w-full rounded-xl border border-emerald-200/80 bg-emerald-50/50 p-4 flex flex-col items-center justify-center text-center">
                            <div className="h-12 w-12 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center mb-2 shadow-sm">
                              <FileSpreadsheet size={28} />
                            </div>
                            <span className="text-xs font-bold text-emerald-950">
                              📊 Excel Invoice
                            </span>
                            <span className="text-[11px] text-emerald-700 mt-0.5">
                              {item.file.name.toLowerCase().endsWith('.csv') ? 'CSV Spreadsheet' : 'Excel Workbook (.xlsx)'}
                            </span>
                            {item.result?.sheet_name && (
                              <span className="mt-2 inline-flex items-center rounded-md bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800">
                                Sheet: {item.result.sheet_name}
                              </span>
                            )}
                            {item.result?.items && item.result.items.length > 0 && (
                              <span className="mt-1 text-[10px] text-emerald-700 font-medium">
                                {item.result.items.length} line items extracted
                              </span>
                            )}
                          </div>
                        ) : (
                          <div className="h-48 w-full rounded-xl border border-slate-200 bg-white p-4 flex flex-col items-center justify-center text-center">
                            <div className="h-12 w-12 rounded-xl bg-red-50 text-red-600 flex items-center justify-center mb-2">
                              <FileText size={28} />
                            </div>
                            <span className="text-xs font-semibold text-slate-700">PDF Document</span>
                            <span className="text-[11px] text-slate-400 mt-0.5">Ready for text extraction</span>
                            <a
                              href={item.previewUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-800"
                            >
                              <Eye size={12} /> Preview in browser
                            </a>
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-slate-200/60 flex items-center justify-between text-xs text-slate-500">
                      <span>Status</span>
                      <span className="font-semibold uppercase tracking-wider text-[11px]">
                        {item.status.replace('_', ' ')}
                      </span>
                    </div>
                  </div>

                  {/* Right Column: Processing Timeline & Results */}
                  <div className="p-6">
                    {/* IN-PROGRESS STATE */}
                    {isProcessing && (
                      <div className="space-y-5">
                        <div className="flex items-center justify-between">
                          <div>
                            <h3 className="font-bold text-slate-900 text-base">Processing document</h3>
                            <p className="text-xs text-slate-500 mt-0.5">{item.stageText}</p>
                          </div>
                          <Badge tone="blue">Analyzing</Badge>
                        </div>

                        {/* Indeterminate Shimmer Progress Bar */}
                        <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                          <div className="h-full w-full animate-shimmer" />
                        </div>

                        {/* Processing Stepper Timeline */}
                        <div className="space-y-3 pt-2">
                          {/* Step 1: Selected & Validated */}
                          <div className="flex items-center gap-3 text-sm">
                            <CheckCircle2 size={18} className="text-emerald-500 shrink-0" />
                            <span className="text-slate-700 font-medium">File selected & client validated</span>
                          </div>

                          {/* Step 2: Upload & Secure Storage */}
                          <div className="flex items-center gap-3 text-sm">
                            {item.status === 'uploading' ? (
                              <div className="h-4 w-4 rounded-full bg-indigo-600 flex items-center justify-center animate-subtle-glow shrink-0">
                                <div className="h-1.5 w-1.5 rounded-full bg-white animate-pulse-dot" />
                              </div>
                            ) : (
                              <CheckCircle2 size={18} className="text-emerald-500 shrink-0" />
                            )}
                            <span
                              className={
                                item.status === 'uploading'
                                  ? 'text-indigo-600 font-semibold'
                                  : 'text-slate-700 font-medium'
                              }
                            >
                              Uploading & saving to private workspace storage
                            </span>
                          </div>

                          {/* Step 3: Text & OCR Extraction */}
                          <div className="flex items-center gap-3 text-sm">
                            {item.status === 'uploading' ? (
                              <div className="h-4 w-4 rounded-full border border-slate-300 shrink-0" />
                            ) : item.status === 'extracting' ? (
                              <div className="h-4 w-4 rounded-full bg-indigo-600 flex items-center justify-center animate-subtle-glow shrink-0">
                                <div className="h-1.5 w-1.5 rounded-full bg-white animate-pulse-dot" />
                              </div>
                            ) : (
                              <CheckCircle2 size={18} className="text-emerald-500 shrink-0" />
                            )}
                            <span
                              className={
                                item.status === 'extracting'
                                  ? 'text-indigo-600 font-semibold'
                                  : item.status === 'uploading'
                                  ? 'text-slate-400'
                                  : 'text-slate-700 font-medium'
                              }
                            >
                              {item.isExcel ? 'Reading workbook & detecting invoice structure' : 'Text extraction & OCR scanning'}
                            </span>
                          </div>

                          {/* Step 4: AI Field Extraction & Validation */}
                          <div className="flex items-center gap-3 text-sm">
                            {item.status === 'validating' ? (
                              <div className="h-4 w-4 rounded-full bg-indigo-600 flex items-center justify-center animate-subtle-glow shrink-0">
                                <div className="h-1.5 w-1.5 rounded-full bg-white animate-pulse-dot" />
                              </div>
                            ) : (
                              <div className="h-4 w-4 rounded-full border border-slate-300 shrink-0" />
                            )}
                            <span
                              className={
                                item.status === 'validating'
                                  ? 'text-indigo-600 font-semibold'
                                  : 'text-slate-400'
                              }
                            >
                              {item.isExcel ? 'Extracting line items, validating totals & duplicate check' : 'AI field extraction, mathematical validation & duplicate check'}
                            </span>
                          </div>
                        </div>

                        <p className="text-[11px] text-slate-400 italic">
                          Document intelligence engine is validating items and invoice metadata...
                        </p>
                      </div>
                    )}

                    {/* COMPLETED SUCCESS STATE */}
                    {item.status === 'completed' && item.result && (
                      <div className="space-y-5 animate-pop-in">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 text-emerald-600 font-bold text-base">
                            <CheckCircle2 size={22} className="text-emerald-500" />
                            <span>{item.isExcel ? 'Excel invoice processed successfully' : 'Invoice processed successfully'}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            {item.isExcel && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-800">
                                📊 Excel Invoice
                              </span>
                            )}
                            <Badge tone="green">PROCESSED</Badge>
                          </div>
                        </div>

                        {/* Extracted Details Grid */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-50 p-4 rounded-2xl border border-slate-100">
                          <div>
                            <span className="block text-[11px] font-medium text-slate-400 uppercase">Invoice #</span>
                            <span className="font-bold text-slate-800 text-sm">
                              {item.result.invoice_number || 'N/A'}
                            </span>
                          </div>
                          <div>
                            <span className="block text-[11px] font-medium text-slate-400 uppercase">Vendor</span>
                            <span className="font-bold text-slate-800 text-sm truncate block" title={item.result.vendor}>
                              {item.result.vendor || 'Unknown'}
                            </span>
                          </div>
                          <div>
                            <span className="block text-[11px] font-medium text-slate-400 uppercase">Date</span>
                            <span className="font-bold text-slate-800 text-sm">{item.result.date || 'N/A'}</span>
                          </div>
                          <div>
                            <span className="block text-[11px] font-medium text-slate-400 uppercase">Total Amount</span>
                            <span className="font-extrabold text-emerald-600 text-sm">
                              {item.result.currency} {Number(item.result.amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                            </span>
                          </div>
                        </div>

                        {/* Financial Math Summary & Validation */}
                        <div className="flex flex-wrap items-center justify-between text-xs gap-2 px-1">
                          <div className="flex items-center gap-4 text-slate-500">
                            <span>Subtotal: {item.result.currency} {Number(item.result.subtotal || 0).toFixed(2)}</span>
                            {Number(item.result.tax || 0) > 0 && (
                              <span>Tax: {item.result.currency} {Number(item.result.tax || 0).toFixed(2)}</span>
                            )}
                            {Number(item.result.discount || 0) > 0 && (
                              <span>Discount: {item.result.currency} {Number(item.result.discount || 0).toFixed(2)}</span>
                            )}
                          </div>
                          <div className="flex items-center gap-1.5 text-emerald-600 font-medium">
                            <CheckCircle2 size={14} />
                            <span>{item.result.validation?.message || 'Calculation validated'}</span>
                          </div>
                        </div>

                        {/* Line Items Toggle if available */}
                        {item.result.items && item.result.items.length > 0 && (
                          <div className="border-t border-slate-100 pt-3">
                            <button
                              onClick={() => toggleLineItems(item.id)}
                              className="flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-800"
                            >
                              {showItemsMap[item.id] ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                              {showItemsMap[item.id] ? 'Hide' : 'Show'} Extracted Line Items ({item.result.items.length})
                            </button>

                            {showItemsMap[item.id] && (
                              <div className="mt-3 space-y-2 bg-slate-50 p-3 rounded-xl border border-slate-100 text-xs">
                                {item.result.items.map((it, idx) => (
                                  <div key={idx} className="flex justify-between items-center py-1 border-b border-slate-200/50 last:border-none">
                                    <span className="font-medium text-slate-700">{it.description} × {it.quantity}</span>
                                    <span className="font-bold text-slate-900">
                                      {item.result?.currency} {Number(it.total).toFixed(2)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Action Buttons */}
                        <div className="flex items-center gap-3 pt-2">
                          <Link
                            href={`/invoices/${item.result.id}`}
                            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 transition"
                          >
                            View Invoice <ArrowRight size={16} />
                          </Link>
                          <button
                            onClick={() => ref.current?.click()}
                            className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition"
                          >
                            Upload Another
                          </button>
                        </div>
                      </div>
                    )}

                    {/* REVIEW REQUIRED STATE */}
                    {item.status === 'review_required' && item.result && (
                      <div className="space-y-4 animate-pop-in">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 text-amber-600 font-bold text-base">
                            <AlertTriangle size={22} className="text-amber-500" />
                            <span>Review Required</span>
                          </div>
                          <Badge tone="amber">NEEDS REVIEW</Badge>
                        </div>

                        {/* Review Reasons Box */}
                        <div className="bg-amber-50/70 border border-amber-200 rounded-2xl p-4 text-xs text-amber-900 space-y-1.5">
                          <p className="font-bold text-amber-800">Why this invoice requires attention:</p>
                          {item.result.review_reasons && item.result.review_reasons.length > 0 ? (
                            <ul className="list-disc list-inside space-y-1 text-amber-800">
                              {item.result.review_reasons.map((reason, idx) => (
                                <li key={idx}>{reason}</li>
                              ))}
                            </ul>
                          ) : (
                            <p>{item.result.validation?.message || 'Extracted values require verification.'}</p>
                          )}
                        </div>

                        {/* Partial Summary */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-50 p-3 rounded-xl border border-slate-100 text-xs">
                          <div>
                            <span className="block text-slate-400">Invoice #</span>
                            <span className="font-semibold text-slate-800">{item.result.invoice_number || 'Unknown'}</span>
                          </div>
                          <div>
                            <span className="block text-slate-400">Vendor</span>
                            <span className="font-semibold text-slate-800">{item.result.vendor || 'Unknown'}</span>
                          </div>
                          <div>
                            <span className="block text-slate-400">Total</span>
                            <span className="font-semibold text-slate-800">
                              {item.result.currency} {Number(item.result.amount || 0).toFixed(2)}
                            </span>
                          </div>
                          <div>
                            <span className="block text-slate-400">Confidence</span>
                            <span className="font-semibold text-amber-600">{Number(item.result.confidence || 0).toFixed(0)}%</span>
                          </div>
                        </div>

                        {/* Actions */}
                        <div className="flex items-center gap-3 pt-2">
                          <Link
                            href={`/invoices/${item.result.id}`}
                            className="inline-flex items-center gap-2 rounded-xl bg-amber-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-amber-700 transition"
                          >
                            Review & Correct <ArrowRight size={16} />
                          </Link>
                          <button
                            onClick={() => ref.current?.click()}
                            className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition"
                          >
                            Upload Another
                          </button>
                        </div>
                      </div>
                    )}

                    {/* DUPLICATE DETECTED STATE */}
                    {item.status === 'duplicate' && item.result && (() => {
                      const existingInvId = item.result.duplicate_of || item.result.existing_invoice_id || item.result.duplicate_invoice_id;
                      const hasValidExistingInvoice = !!existingInvId && Number(existingInvId) > 0;
                      const dupInvoiceNumber = item.result.duplicate_invoice_number || item.result.invoice_number;
                      const hasDupInvoiceNumber = !!dupInvoiceNumber && String(dupInvoiceNumber).trim().length > 0 && String(dupInvoiceNumber).toLowerCase() !== 'unknown' && String(dupInvoiceNumber).toLowerCase() !== 'n/a';

                      return (
                        <div className="space-y-4 animate-pop-in">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-rose-600 font-bold text-base">
                              <Copy size={22} className="text-rose-500" />
                              <span>Possible Duplicate Detected</span>
                            </div>
                            <Badge tone="red">DUPLICATE</Badge>
                          </div>

                          <div className="bg-rose-50/70 border border-rose-200 rounded-2xl p-4 text-xs text-rose-900 space-y-1.5">
                            <p className="font-bold text-rose-800">
                              {hasDupInvoiceNumber
                                ? `Invoice #${dupInvoiceNumber} matches an existing record in your organization.`
                                : `An identical invoice file or record matches an existing invoice in your organization.`}
                            </p>
                            {item.result.duplicate_vendor && (
                              <p>Existing Vendor: {item.result.duplicate_vendor}</p>
                            )}
                            {item.result.duplicate_total !== undefined && item.result.duplicate_total !== null && !isNaN(Number(item.result.duplicate_total)) && (
                              <p>Existing Amount: {item.result.currency || 'USD'} {Number(item.result.duplicate_total).toFixed(2)}</p>
                            )}
                          </div>

                          {/* Actions */}
                          <div className="flex flex-wrap items-center gap-3 pt-2">
                            {hasValidExistingInvoice && (
                              <Link
                                href={`/invoices/${existingInvId}`}
                                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 transition"
                              >
                                View Existing Invoice <ArrowRight size={16} />
                              </Link>
                            )}
                            {item.result.id && Number(item.result.id) > 0 && (
                              <Link
                                href={`/invoices/${item.result.id}`}
                                className="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition"
                              >
                                Review Anyway
                              </Link>
                            )}
                            <button
                              onClick={() => ref.current?.click()}
                              className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition"
                            >
                              Upload Another
                            </button>
                          </div>
                        </div>
                      );
                    })()}

                    {/* UNSUPPORTED DOCUMENT STATE */}
                    {item.status === 'unsupported' && (
                      <div className="space-y-4 animate-pop-in">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 text-slate-700 font-bold text-base">
                            <FileX size={22} className="text-slate-500" />
                            <span>{item.isExcel ? 'Unsupported Spreadsheet' : 'Unsupported Document'}</span>
                          </div>
                          <Badge tone="slate">UNSUPPORTED</Badge>
                        </div>

                        <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 text-xs text-slate-700 space-y-2">
                          <p className="font-bold text-slate-800 text-sm">
                            {item.result?.message || (item.isExcel
                              ? "This Excel file could be opened successfully, but we couldn't identify it as an invoice."
                              : "We couldn't identify this file as a supported invoice or receipt.")}
                          </p>
                          {item.isExcel ? (
                            <div className="space-y-1.5 pt-1">
                              <p className="flex items-center gap-1.5 text-emerald-700 font-semibold">
                                <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
                                <span>File format supported (.xlsx / .xls)</span>
                              </p>
                              <p className="text-slate-600 leading-relaxed">
                                SecureDoc AI can read this workbook, but the spreadsheet does not contain billing information (such as an invoice number, vendor, or itemized pricing table). Arbitrary datasets, website monitoring, employee logs, or random spreadsheets are not recorded as invoices.
                              </p>
                              {item.result?.details && (
                                <p className="text-[11px] text-slate-500 italic mt-1 bg-white p-2 rounded-lg border border-slate-200/60">
                                  {item.result.details}
                                </p>
                              )}
                            </div>
                          ) : (
                            <p className="text-slate-500">
                              SecureDoc AI is specialized for processing business invoices, bills, and purchase receipts. Non-billing files (such as CVs, general articles, or unformatted text) are not recorded as invoices.
                            </p>
                          )}
                        </div>

                        <div className="pt-2">
                          <button
                            onClick={() => ref.current?.click()}
                            className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800 transition"
                          >
                            <UploadCloud size={16} /> Upload another file
                          </button>
                        </div>
                      </div>
                    )}

                    {/* FAILED STATE */}
                    {item.status === 'failed' && (
                      <div className="space-y-4 animate-shake">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 text-rose-600 font-bold text-base">
                            <AlertCircle size={22} className="text-rose-500" />
                            <span>Processing Failed</span>
                          </div>
                          <Badge tone="red">FAILED</Badge>
                        </div>

                        <div className="bg-rose-50 border border-rose-200 rounded-2xl p-4 text-xs text-rose-800">
                          <p className="font-bold">We couldn't process this document.</p>
                          <p className="mt-1 text-rose-700">{item.error}</p>
                        </div>

                        <div className="flex items-center gap-3 pt-2">
                          <button
                            onClick={() => handleRetry(item)}
                            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 transition"
                          >
                            <RefreshCw size={16} /> Try Again
                          </button>
                          <button
                            onClick={() => ref.current?.click()}
                            className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition"
                          >
                            Upload Another
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </Shell>
  );
}