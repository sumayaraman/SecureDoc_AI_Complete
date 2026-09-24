'use client';
import { useRef, useState } from 'react';
import { Shell } from '../../components/shell';
import { Card } from '../../components/ui';
import { uploadFile } from '../../lib/api';
import { UploadCloud, CheckCircle2, AlertCircle } from 'lucide-react';
import Link from 'next/link';

export default function Upload() {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any[]>([]);
  const [error, setError] = useState('');

  async function go(files: FileList | null) {
    if (!files) return;
    setBusy(true);
    setError('');
    for (const f of Array.from(files)) {
      try {
        const x = await uploadFile(f);
        setResult(v => [x, ...v]);
      } catch (e: any) {
        setError(`${f.name}: ${e.message}`);
      }
    }
    setBusy(false);
  }

  return (
    <Shell>
      <div>
        <p className="text-sm font-medium text-indigo-600">Document intake</p>
        <h1 className="mt-1 text-2xl font-bold">Upload invoices</h1>
        <p className="mt-1 text-sm text-slate-500">
          SecureDoc AI extracts and validates invoice data automatically.
        </p>
      </div>
      <Card className="mt-6 border-dashed p-10 text-center">
        <input
          ref={ref}
          type="file"
          multiple
          accept="application/pdf,image/jpeg,image/png"
          className="hidden"
          onChange={e => go(e.target.files)}
        />
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-indigo-50 text-indigo-600">
          <UploadCloud size={28} />
        </div>
        <p className="mt-4 font-bold">Drop invoices here</p>
        <p className="text-sm text-slate-500">PDF, JPG or PNG</p>
        <button
          onClick={() => ref.current?.click()}
          className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white"
        >
          {busy ? 'Uploading…' : 'Choose files'}
        </button>
      </Card>
      {error && (
        <p className="mt-2 flex items-center gap-1 text-sm text-red-600">
          <AlertCircle size={14} /> {error}
        </p>
      )}
      {result.map((r, i) => (
        <Card key={i} className="mt-3 flex items-center gap-3 p-4">
          <CheckCircle2 className="text-green-500" size={20} />
          <div className="flex-1 text-sm">
            <p className="font-medium">{r.filename}</p>
          </div>
          {r.invoice_id && (
            <Link href={`/invoices/${r.invoice_id}`} className="text-sm text-indigo-600 underline">
              View
            </Link>
          )}
        </Card>
      ))}
    </Shell>
  );
}