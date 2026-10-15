"use client";

import { Copy } from "lucide-react";
import { toast } from "sonner";
import { Modal } from "@/components/modals/modal";
import { Button } from "@/components/ui/button";

export interface ShownCredential {
  label: string;
  username: string;
  temp_password: string;
}

/** Temporary passwords exist only in the registration response, so this is the one chance to hand them over. */
export function CredentialsModal({ credentials, note, onDone }: { credentials: ShownCredential[]; note?: string; onDone: () => void }) {
  const text = credentials.map((c) => `${c.label}: ${c.username} / ${c.temp_password}`).join("\n");
  return (
    <Modal open onOpenChange={(o) => !o && onDone()} title="Login details" description="Write these down or copy them now. They won't be shown again."
      footer={<>
        <Button variant="outline" onClick={() => navigator.clipboard.writeText(text).then(() => toast.success("Copied"), () => toast.error("Couldn't copy"))}><Copy className="h-4 w-4" />Copy all</Button>
        <Button onClick={onDone}>Done</Button>
      </>}>
      <dl className="space-y-3">
        {credentials.map((c) => (
          <div key={c.label} className="rounded-md border border-border p-3 text-sm">
            <dt className="mb-1 font-semibold">{c.label}</dt>
            <dd className="grid grid-cols-[6rem_1fr] gap-y-1 font-mono">
              <span className="font-sans text-muted-foreground">Username</span><span className="select-all">{c.username}</span>
              <span className="font-sans text-muted-foreground">Password</span><span className="select-all">{c.temp_password}</span>
            </dd>
          </div>
        ))}
        {note ? <p className="text-sm text-muted-foreground">{note}</p> : null}
      </dl>
    </Modal>
  );
}
