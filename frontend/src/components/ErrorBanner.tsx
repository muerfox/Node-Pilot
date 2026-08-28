import { ApiError } from "@/lib/api";

export default function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof ApiError ? `${error.message} (${error.code})` : error instanceof Error ? error.message : "Something went wrong.";
  return <div className="rounded-md border border-status-error/30 bg-status-error/10 px-3 py-2 text-sm text-status-error">{message}</div>;
}
