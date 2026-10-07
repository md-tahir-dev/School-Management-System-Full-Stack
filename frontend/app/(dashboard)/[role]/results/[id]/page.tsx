"use client";

import { ResultCardPage } from "@/components/results/result-card";
import { PageBoundary } from "@/components/ui/state-views";

export default function ResultPage({ params }: { params: { id: string } }) {
  return <PageBoundary><ResultCardPage resultId={params.id} /></PageBoundary>;
}
