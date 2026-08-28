import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "@/components/Layout";
import { FullPageSpinner } from "@/components/Spinner";
import { useAuth } from "@/lib/auth";
import AuditLogPage from "@/pages/AuditLogPage";
import BackupsPage from "@/pages/BackupsPage";
import DashboardPage from "@/pages/DashboardPage";
import ImagesPage from "@/pages/ImagesPage";
import JobsPage from "@/pages/JobsPage";
import LoginPage from "@/pages/LoginPage";
import NetworksPage from "@/pages/NetworksPage";
import NodeDetailPage from "@/pages/NodeDetailPage";
import NodesListPage from "@/pages/NodesListPage";
import NotFoundPage from "@/pages/NotFoundPage";
import OrganizationsPage from "@/pages/OrganizationsPage";
import SearchResultsPage from "@/pages/SearchResultsPage";
import StoragePage from "@/pages/StoragePage";
import TemplatesPage from "@/pages/TemplatesPage";
import TokensPage from "@/pages/TokensPage";
import UsersPage from "@/pages/UsersPage";
import VMCreateWizardPage from "@/pages/VMCreateWizardPage";
import VMDetailPage from "@/pages/VMDetailPage";
import VMsListPage from "@/pages/VMsListPage";
import WebhooksPage from "@/pages/WebhooksPage";

function ProtectedLayout() {
  const { status } = useAuth();
  if (status === "loading") return <FullPageSpinner />;
  if (status === "unauthenticated") return <Navigate to="/login" replace />;
  return <Layout />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<ProtectedLayout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/search" element={<SearchResultsPage />} />

        <Route path="/nodes" element={<NodesListPage />} />
        <Route path="/nodes/:uuid" element={<NodeDetailPage />} />

        <Route path="/vms" element={<VMsListPage />} />
        <Route path="/vms/new" element={<VMCreateWizardPage />} />
        <Route path="/vms/:uuid" element={<VMDetailPage />} />

        <Route path="/networks" element={<NetworksPage />} />
        <Route path="/storage" element={<StoragePage />} />
        <Route path="/images" element={<ImagesPage />} />

        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/backups" element={<BackupsPage />} />

        <Route path="/users" element={<UsersPage />} />
        <Route path="/organizations" element={<OrganizationsPage />} />
        <Route path="/tokens" element={<TokensPage />} />
        <Route path="/webhooks" element={<WebhooksPage />} />
        <Route path="/audit" element={<AuditLogPage />} />

        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
