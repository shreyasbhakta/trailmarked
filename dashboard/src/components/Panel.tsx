export default function Panel({ title, children, right }: { title?: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="border border-[var(--border)] bg-[var(--bg-panel)] rounded-lg">
      {title && (
        <div className="px-4 py-2.5 border-b border-[var(--border)] flex items-center justify-between">
          <div className="text-xs font-medium uppercase tracking-wide text-[var(--text-dim)]">{title}</div>
          {right}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}
