import { useState } from 'react';
import { X, Download, FileText, Presentation, FileCode, BookOpen } from 'lucide-react';

type Props = {
  sessionId: string;
  revision: number;
  onClose: () => void;
};

const FORMATS = [
  { key: 'markdown', label: 'Markdown', icon: <FileText size={16} />, desc: 'Raw markdown for further editing' },
  { key: 'docx', label: 'Word (DOCX)', icon: <BookOpen size={16} />, desc: 'Formatted Word document with ToC' },
  { key: 'slides', label: 'Slide Outline', icon: <Presentation size={16} />, desc: 'Speaker notes structured for slides' },
  { key: 'json', label: 'JSON', icon: <FileCode size={16} />, desc: 'Structured data for programmatic use' },
];

const TEMPLATES = [
  { key: '', label: 'No rewrite', desc: 'Export as-is' },
  { key: 'whitepaper', label: 'Whitepaper', desc: 'Formal academic style' },
  { key: 'conference_talk', label: 'Conference Talk', desc: 'DEF CON / Black Hat style' },
  { key: 'blog_post', label: 'Blog Post', desc: 'Engaging developer blog' },
  { key: 'internal_report', label: 'Internal Report', desc: 'Concise stakeholder report' },
];

export default function ExportModal({ sessionId, revision, onClose }: Props) {
  const [format, setFormat] = useState('markdown');
  const [template, setTemplate] = useState('');
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      const body = JSON.stringify({ format, template: template || null, revision });
      const res = await fetch(`/api/sessions/${sessionId}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      });

      if (format === 'json') {
        const data = await res.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        downloadBlob(blob, `narrative-rev${revision}.json`);
      } else {
        const blob = await res.blob();
        const ext = format === 'docx' ? 'docx' : 'md';
        downloadBlob(blob, `narrative-rev${revision}.${ext}`);
      }
      onClose();
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl w-[520px] max-h-[80vh] overflow-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-[var(--border)]">
          <h2 className="font-semibold">Export Narrative</h2>
          <button onClick={onClose} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"><X size={18} /></button>
        </div>

        <div className="p-4 space-y-4">
          {/* Format */}
          <div>
            <label className="text-xs font-medium text-[var(--text-secondary)] mb-2 block">Format</label>
            <div className="grid grid-cols-2 gap-2">
              {FORMATS.map(f => (
                <button
                  key={f.key}
                  onClick={() => setFormat(f.key)}
                  className={`flex items-center gap-2 p-3 rounded-lg border text-left text-sm transition-colors ${
                    format === f.key
                      ? 'border-[var(--accent-blue)] bg-[var(--accent-blue)]/10 text-[var(--text-primary)]'
                      : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--text-muted)]'
                  }`}
                >
                  {f.icon}
                  <div>
                    <div className="font-medium">{f.label}</div>
                    <div className="text-xs text-[var(--text-muted)]">{f.desc}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Template */}
          <div>
            <label className="text-xs font-medium text-[var(--text-secondary)] mb-2 block">
              Template (optional rewrite)
            </label>
            <div className="space-y-1">
              {TEMPLATES.map(t => (
                <button
                  key={t.key}
                  onClick={() => setTemplate(t.key)}
                  className={`w-full flex items-center justify-between p-2.5 rounded border text-sm text-left transition-colors ${
                    template === t.key
                      ? 'border-[var(--accent-blue)] bg-[var(--accent-blue)]/10'
                      : 'border-[var(--border)] hover:border-[var(--text-muted)]'
                  }`}
                >
                  <span className="font-medium">{t.label}</span>
                  <span className="text-xs text-[var(--text-muted)]">{t.desc}</span>
                </button>
              ))}
            </div>
            {template && (
              <p className="text-xs text-[var(--accent-yellow)] mt-2">
                Template rewrite will use Opus and may take 30-60 seconds.
              </p>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2 p-4 border-t border-[var(--border)]">
          <button onClick={onClose} className="px-4 py-2 text-sm text-[var(--text-secondary)] border border-[var(--border)] rounded">
            Cancel
          </button>
          <button
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-[var(--accent-blue)] text-black font-medium rounded disabled:opacity-50"
          >
            <Download size={14} />
            {exporting ? 'Exporting...' : 'Export'}
          </button>
        </div>
      </div>
    </div>
  );
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
