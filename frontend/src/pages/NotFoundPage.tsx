import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-24 text-center">
      <p className="text-2xl font-semibold text-surface-100">404</p>
      <p className="text-sm text-surface-400">This page doesn't exist.</p>
      <Link to="/" className="btn-secondary mt-3">
        Back to Dashboard
      </Link>
    </div>
  );
}
