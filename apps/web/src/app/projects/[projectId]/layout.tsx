"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { use } from "react";
import type { ReactNode } from "react";

import { useDeclaredClassification, useResource } from "@/components/shell";
import { api } from "@/lib/api";
import type { ProjectDashboard } from "@/lib/types";

const TABS = [
  { slug: "", label: "Readiness" },
  { slug: "mission", label: "Mission" },
  { slug: "systems", label: "Systems" },
  { slug: "plan", label: "Plan" },
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

  useDeclaredClassification(project?.classification);

  return (
    <div className="space-y-4">
      <div className="animate-rise flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link href="/" className="link-underline text-xs text-muted hover:text-ink">
            Portfolio
          </Link>
          <h1 className="mt-1 truncate text-xl font-normal text-ink">
            {project?.name ?? <span className="skeleton inline-block h-5 w-40 align-middle" />}
          </h1>
          {data?.mission ? (
            <p className="mt-0.5 max-w-3xl text-sm text-muted">{data.mission.mission}</p>
          ) : null}
        </div>

        {project ? (
          <div className="flex flex-wrap items-center gap-1.5 text-2xs">
            {[project.classification, project.impact_level, project.deployment_environment]
              .filter(Boolean)
              .map((chip) => (
                <span key={String(chip)} className="border border-line px-1.5 py-0.5 text-muted">
                  {chip}
                </span>
              ))}
          </div>
        ) : null}
      </div>

      {/* The active tab is marked by a sliding hairline, which makes the change
          of section legible without a colour change. */}
      <nav className="flex gap-4 overflow-x-auto border-b border-line">
        {TABS.map((tab) => {
          const href = tab.slug ? `${base}/${tab.slug}` : base;
          const active = tab.slug ? pathname.startsWith(href) : pathname === base;
          return (
            <Link
              key={tab.slug || "root"}
              href={href}
              className={`relative shrink-0 pb-2 pt-1 text-sm transition-colors duration-150 ease-out ${
                active ? "text-ink" : "text-muted hover:text-ink"
              }`}
            >
              {tab.label}
              {active ? (
                <motion.span
                  layoutId="project-tab"
                  className="absolute -bottom-px left-0 right-0 h-px bg-ink"
                  transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                />
              ) : null}
            </Link>
          );
        })}
      </nav>

      {children}
    </div>
  );
}
