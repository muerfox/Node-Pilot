import type { ReactNode } from "react";

export default function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-surface-800 py-16 text-center">
      <p className="text-sm font-medium text-surface-300">{title}</p>
      {description && <p className="max-w-sm text-xs text-surface-500">{description}</p>}
      {action}
    </div>
  );
}
