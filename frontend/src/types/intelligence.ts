export interface GithubIntelligence {
  available: boolean;
  message?: string | null;
  full_name?: string | null;
  description?: string | null;
  stars: number;
  forks: number;
  watchers: number;
  open_issues: number;
  default_branch?: string | null;
  license?: string | null;
  html_url?: string | null;
}

export interface Vulnerability {
  id: string;
  summary?: string | null;
  severity: "Critical" | "High" | "Moderate" | "Low" | "Unknown";
  affected_versions: string[];
  fixed_versions: string[];
  references: string[];
  ecosystem: string;
  package: string;
  installed_version: string;
}

export interface Dependency {
  ecosystem: "npm" | "PyPI";
  name: string;
  installed_version?: string | null;
  requested_version?: string | null;
  latest_version?: string | null;
  description?: string | null;
  dependency_type: string;
  source_file: string;
  status: "up-to-date" | "outdated" | "vulnerable" | "unknown";
  vulnerabilities: Vulnerability[];
}

export interface DependenciesResponse {
  available: boolean;
  message?: string | null;
  checked_at: string;
  dependencies: Dependency[];
}

export interface SecurityResponse {
  available: boolean;
  message?: string | null;
  checked_at: string;
  dependencies_scanned: number;
  severity_counts: Record<string, number>;
  vulnerabilities: Vulnerability[];
}
