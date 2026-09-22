"use client";

import { Toaster as Sonner, toast } from "sonner";

/** Global toast host. Use `toast.success("Saved")` / `toast.error(...)` anywhere on the client. */
export function Toaster() {
  return (
    <Sonner
      position="top-right"
      closeButton
      toastOptions={{
        classNames: {
          toast: "!rounded-lg !border !border-border !bg-card !text-foreground !shadow-lg !font-sans",
          description: "!text-muted-foreground",
        },
      }}
    />
  );
}

export { toast };
