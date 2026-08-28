import { Outlet } from "react-router-dom";

import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";

export default function Layout() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-surface-950">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="flex-1 overflow-y-auto px-6 py-5">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
