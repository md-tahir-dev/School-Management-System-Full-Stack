import * as React from "react";
import { cn } from "@/lib/utils";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...props }, ref) => (
    <select
      ref={ref}
      className={cn("h-10 rounded-md border border-border bg-card px-3 text-sm disabled:cursor-not-allowed disabled:opacity-50", className)}
      {...props}
    />
  ),
);
Select.displayName = "Select";
