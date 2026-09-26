"use client";

import { Walkthrough } from "@/components/onboarding";
import { PageTitle } from "@/components/ui";
import { TourWelcome, tourEnabled } from "@/tour";

export default function WelcomePage() {
  // The tour replaces the walkthrough when it is on; see src/tour/flags.ts.
  if (tourEnabled()) return <TourWelcome />;
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
