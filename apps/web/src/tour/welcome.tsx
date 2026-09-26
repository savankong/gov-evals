"use client";

import { useEffect, useState } from "react";

import { Button, Card, Note, PageTitle, Tag } from "@/components/ui";

import { PATH_COPY, UI } from "./copy";
import type { Progress } from "./controller";
import { useTour } from "./provider";
import { PATHS } from "./steps";
import { PATH_IDS } from "./types";

/** /welcome with the tour on: the two paths, each started from its preview. */
export function TourWelcome() {
  const { controller, snapshot } = useTour();
  const [progress, setProgress] = useState<Progress | null>(null);
  useEffect(() => {
    setProgress(controller?.progress() ?? null);
  }, [controller, snapshot]);

  if (!controller) return null;

  return (
    <div className="space-y-4">
      <PageTitle title={UI.welcome.title} subtitle={UI.welcome.subtitle} />
      <div className="grid gap-4 md:grid-cols-2">
        {PATH_IDS.map((id) => {
          const copy = PATH_COPY[id];
          const done = progress?.path === id && progress.status === "completed";
          return (
            <Card key={id}>
              <div className="flex h-full flex-col px-4 py-4">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-2xs uppercase tracking-wider text-faint">
                    {copy.name} · {PATHS[id].steps.length} steps
                  </span>
                  {done ? <Tag>{UI.welcome.done}</Tag> : null}
                </div>
                <h2 className="mt-2 font-serif text-xl text-ink">{copy.preview.title}</h2>
                <p className="mt-1 text-sm text-muted">{copy.who}</p>
                <div className="mt-4">
                  <Button variant="primary" onClick={() => controller.openPreview(id)}>
                    {done ? UI.welcome.replay(copy.name) : UI.welcome.start(copy.name)}
                  </Button>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
      <Note>{UI.welcome.sample}</Note>
    </div>
  );
}
