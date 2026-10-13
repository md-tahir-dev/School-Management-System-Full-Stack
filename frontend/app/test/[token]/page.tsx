import { ClipboardList } from "lucide-react";
import Link from "next/link";
import { Card } from "@/components/ui/card";

// Guest mode is not supported: share links just send students to sign in.
export default function PublicTestPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="flex max-w-md flex-col items-center gap-3 p-10 text-center">
        <ClipboardList className="h-8 w-8 text-primary" aria-hidden />
        <h1 className="text-lg font-semibold">Sign in to take this test</h1>
        <p className="text-sm text-muted-foreground">Tests are only available to signed-in students.</p>
        <Link href="/login?next=/student/tests" className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground">Sign in</Link>
      </Card>
    </main>
  );
}
