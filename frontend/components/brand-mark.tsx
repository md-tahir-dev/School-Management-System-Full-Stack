import { GraduationCap } from "lucide-react";
import { cn } from "@/lib/utils";

/** The school's uploaded logo, or a generic mark until one is set (Settings > School profile). */
export function BrandMark({ logoUrl, className }: { logoUrl?: string | null; className?: string }) {
  return logoUrl ? (
    // eslint-disable-next-line @next/next/no-img-element -- user-uploaded, served via the API rewrite
    <img src={logoUrl} alt="" className={cn("rounded-md bg-white object-contain p-0.5", className)} />
  ) : (
    <span className={cn("flex items-center justify-center rounded-md bg-secondary text-secondary-foreground", className)}>
      <GraduationCap className="h-5 w-5" aria-hidden />
    </span>
  );
}
