import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "@/lib/auth";

export default function Topbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  function handleSearch(event: FormEvent) {
    event.preventDefault();
    if (query.trim()) navigate(`/search?q=${encodeURIComponent(query.trim())}`);
  }

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-surface-800 bg-surface-900/40 px-4">
      <form onSubmit={handleSearch} className="w-full max-w-md">
        <input
          className="input"
          placeholder="Search VMs, nodes, IPs, storage, images, jobs, users..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </form>

      <div className="flex items-center gap-3 pl-4">
        <span className="text-sm text-surface-300">{user?.username}</span>
        <button className="btn-ghost" onClick={logout}>
          Sign out
        </button>
      </div>
    </header>
  );
}
