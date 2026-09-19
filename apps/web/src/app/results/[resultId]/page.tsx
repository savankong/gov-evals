"use client";

import { useRouter } from "next/navigation";
import { use, useEffect } from "react";

import { EvidencePanel } from "@/components/evidence-panel";
import { useDeclaredClassification, useResource } from "@/components/shell";
import { ErrorNote, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import type { ResultDetail } from "@/lib/types";

/**
 * A direct link to one result.
 *
 * Evidence normally opens as a panel beside its run. Arriving here from a
 * bookmark or a report, the panel opens over the run it belongs to, so closing
 * it leaves the reader in the list rather than on a dead end.
 */
export default function ResultPage({ params }: { params: Promise<{ resultId: string }> }) {
  const { resultId } = use(params);
  const router = useRouter();
  const { data, error, loading } = useResource<ResultDetail & { classification?: string | null }>(
    () => api.get<ResultDetail>(`/results/${resultId}`),
    [resultId],
  );

  useDeclaredClassification(data?.classification);

  const runId = data?.run?.id;
  useEffect(() => {
    if (runId) router.replace(`/runs/${runId}?result=${resultId}`);
  }, [runId, resultId, router]);

  if (loading) return <Spinner label="Loading evidence" />;
  if (error) return <ErrorNote message={error} />;

  return <EvidencePanel resultId={resultId} onClose={() => router.back()} />;
}
