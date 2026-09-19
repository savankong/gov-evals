"use client";

import { Walkthrough } from "@/components/onboarding";
import { PageTitle } from "@/components/ui";

export default function WelcomePage() {
  return (
    <div className="space-y-4">
      <PageTitle
        title="Getting started"
        subtitle="What this product is, and where this account actually is in the workflow."
      />
      <Walkthrough />
    </div>
  );
}
