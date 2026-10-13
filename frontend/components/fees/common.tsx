"use client";

import { Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { apiBlob, errorText, saveBlob } from "@/lib/api";

export async function downloadPdf(path: string, filename: string) {
  try {
    saveBlob(await apiBlob(path), filename);
  } catch (e) {
    toast.error(errorText(e, "Couldn't download the PDF"));
  }
}

export function PdfButton({ path, filename, label = "PDF" }: { path: string; filename: string; label?: string }) {
  return (
    <Button size="sm" variant="outline" onClick={() => downloadPdf(path, filename)}>
      <Download className="h-3.5 w-3.5" aria-hidden />{label}
    </Button>
  );
}

export const currentMonth = () => new Date().toISOString().slice(0, 7);
