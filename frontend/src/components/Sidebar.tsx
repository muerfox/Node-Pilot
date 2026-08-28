import { NavLink } from "react-router-dom";

interface NavItem {
  to: string;
  label: string;
}

const SECTIONS: { title: string; items: NavItem[] }[] = [
  { title: "", items: [{ to: "/", label: "Dashboard" }] },
  {
    title: "Infrastructure",
    items: [
      { to: "/nodes", label: "Nodes" },
      { to: "/vms", label: "Virtual Machines" },
      { to: "/networks", label: "Networks" },
      { to: "/storage", label: "Storage" },
      { to: "/images", label: "Images" },
    ],
  },
  {
    title: "Automation",
    items: [
      { to: "/templates", label: "Templates" },
      { to: "/jobs", label: "Jobs" },
      { to: "/backups", label: "Backups" },
    ],
  },
  {
    title: "Administration",
    items: [
      { to: "/users", label: "Users" },
      { to: "/organizations", label: "Organizations" },
      { to: "/tokens", label: "API Tokens" },
      { to: "/webhooks", label: "Webhooks" },
      { to: "/audit", label: "Audit Logs" },
    ],
  },
];

export default function Sidebar() {
  return (
    <nav className="flex h-full w-56 shrink-0 flex-col gap-5 overflow-y-auto border-r border-surface-800 bg-surface-900/60 px-3 py-4">
      <div className="flex items-center gap-2 px-2">
        <svg width="22" height="22" viewBox="0 0 32 32" className="shrink-0 rounded bg-surface-950">
          <path d="M9 22V10l14 12V10" stroke="#38bdf8" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="text-sm font-semibold text-surface-50">NodePilot</span>
      </div>

      {SECTIONS.map((section) => (
        <div key={section.title || "root"}>
          {section.title && <p className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-wider text-surface-500">{section.title}</p>}
          <div className="flex flex-col gap-0.5">
            {section.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `rounded-md px-2.5 py-1.5 text-sm transition-colors ${
                    isActive ? "bg-accent-500/15 font-medium text-accent-400" : "text-surface-300 hover:bg-surface-800 hover:text-surface-50"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </div>
        </div>
      ))}
    </nav>
  );
}
