import { useQuery } from "@tanstack/react-query";

import { nodes, organizations, projects, storagePools } from "@/lib/resources";

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  className?: string;
}

export function OrganizationSelect({ value, onChange, required, className = "input" }: SelectProps) {
  const { data } = useQuery({ queryKey: ["organizations", "picker"], queryFn: () => organizations.list({ page_size: 100 }) });
  return (
    <select className={className} value={value} required={required} onChange={(e) => onChange(e.target.value)}>
      <option value="">Select an organization...</option>
      {data?.results.map((org) => (
        <option key={org.uuid} value={org.uuid}>
          {org.name}
        </option>
      ))}
    </select>
  );
}

export function ProjectSelect({ organization, value, onChange, required, className = "input" }: SelectProps & { organization: string }) {
  const { data } = useQuery({
    queryKey: ["projects", "picker", organization],
    queryFn: () => projects.list({ organization, page_size: 100 }),
    enabled: !!organization,
  });
  return (
    <select className={className} value={value} required={required} disabled={!organization} onChange={(e) => onChange(e.target.value)}>
      <option value="">{organization ? "Select a project..." : "Select an organization first"}</option>
      {data?.results.map((project) => (
        <option key={project.uuid} value={project.uuid}>
          {project.name}
        </option>
      ))}
    </select>
  );
}

export function NodeSelect({ organization, value, onChange, className = "input" }: SelectProps & { organization?: string }) {
  const { data } = useQuery({
    queryKey: ["nodes", "picker", organization],
    queryFn: () => nodes.list({ organization, page_size: 100 }),
  });
  return (
    <select className={className} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Auto (let the scheduler pick)</option>
      {data?.results.map((node) => (
        <option key={node.uuid} value={node.uuid} disabled={node.status !== "ONLINE"}>
          {node.name} ({node.status})
        </option>
      ))}
    </select>
  );
}

export function StorageSelect({ node, value, onChange, required, className = "input" }: SelectProps & { node?: string }) {
  const { data } = useQuery({
    queryKey: ["storages", "picker", node],
    queryFn: () => storagePools.list({ node, page_size: 100 }),
  });
  return (
    <select className={className} value={value} required={required} onChange={(e) => onChange(e.target.value)}>
      <option value="">Select a storage pool...</option>
      {data?.results.map((pool) => (
        <option key={pool.uuid} value={pool.uuid}>
          {pool.name} ({pool.type})
        </option>
      ))}
    </select>
  );
}
