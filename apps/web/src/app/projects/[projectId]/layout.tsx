"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { use } from "react";
import type { ReactNode } from "react";

import { useDeclaredClassification, useResource } from "@/components/shell";
import { api } from "@/lib/api";
import type { ProjectDashboard } from "@/lib/types";

const TABS = [
  { slug: "", label: "Readiness" },
  { slug: "plan", label: "Evaluation plan" },
  { slug: "campaigns", label: "Campaigns" },
  { slug: "findings", label: "Findings" },
  { slug: "compare", label: "Comparison" },
  { slug: "assurance", label: "Assurance" },
  { slug: "frameworks", label: "Frameworks" },
  { slug: "scenarios", label: "Scenarios" },
  { slug: "reports", label: "Reports" },
];

export default function ProjectLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = use(params);
  const pathname = usePathname();
  const { data } = useResource<ProjectDashboard>(
    () => api.get<ProjectDashboard>(`/projects/${projectId}/dashboard`),
    [projectId],
  );

  const base = `/projects/${projectId}`;
  const project = data?.project;

  // Every tab under a project carries that project's marking.
  useDeclaredClassification(project?.classification);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link href="/" className="text-xs text-muted hover:text-ink hover:underline">
            ← Portfolio
          </Link>
          <h1 className="mt-1 truncate text-lg font-semibold tracking-tight">
            {project?.name ?? "Project"}
          </h1>
          {data?.mission ? (
            <p className="mt-0.5 max-w-3xl text-sm text-muted">{data.mission.mission}</p>
          ) : null}
        </div>

        {project ? (
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
            <span className="rounded border border-line px-2 py-1 text-muted">
              {project.classification}
            </span>
            {project.impact_level ? (
              <span className="rounded border border-line px-2 py-1 text-muted">
                {project.impact_level}
              </span>
            ) : null}
            {project.deployment_environment ? (
              <span className="rounded border border-line px-2 py-1 text-muted">
                {project.deployment_environment}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>

      <nav className="flex gap-1 overflow-x-auto border-b border-line">
        {TABS.map((tab) => {
          const href = tab.slug ? `${base}/${tab.slug}` : base;
          const active = tab.slug ? pathname.startsWith(href) : pathname === base;
          return (
            <Link
              key={tab.slug || "root"}
              href={href}
              className={`-mb-px shrink-0 border-b-2 px-3 py-2 text-sm transition-colors ${
                active
                  ? "border-[rgb(var(--accent))] font-medium text-ink"
                  : "border-transparent text-muted hover:text-ink"
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>

      {children}
    </div>
  );
}
