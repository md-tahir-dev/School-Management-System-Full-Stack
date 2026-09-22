import { ClipboardList } from "lucide-react";
import { Card } from "@/components/ui/card";

// Public share-link landing page. The real test-taking flow arrives with online tests (phase 5).
export default function PublicTestPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="flex max-w-md flex-col items-center gap-3 p-10 text-center">
        <ClipboardList className="h-8 w-8 text-primary" aria-hidden />
        <h1 className="text-lg font-semibold">Online tests aren't open yet</h1>
        <p className="text-sm text-muted-foreground">Ask your teacher to send this link again once tests are enabled.</p>
      </Card>
    </main>
  );
}
