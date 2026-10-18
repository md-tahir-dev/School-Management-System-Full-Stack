import "@fontsource-variable/figtree";
import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers } from "./providers";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
// Static pages (login, change-password) are re-rendered every 60 s so a renamed school shows up without a rebuild.
export const revalidate = 60;

/** White-label: the tab title and favicon come from the school's settings, not the code. */
export async function generateMetadata(): Promise<Metadata> {
  let name = "School";
  let icon: string | null = null;
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/public/config`, { next: { revalidate: 60 }, signal: AbortSignal.timeout(3000) });
    if (res.ok) {
      const config = (await res.json()) as { school_name: string; logo_url: string | null; favicon_url?: string | null };
      name = config.school_name;
      icon = config.favicon_url ?? config.logo_url;
    }
  } catch {
    // API unreachable (e.g. during `next build`): keep the neutral fallback.
  }
  return {
    title: { default: name, template: `%s | ${name}` },
    description: "Students, teachers, fees, results and more in one place.",
    icons: icon ? { icon, apple: icon } : undefined,
  };
}

export const viewport: Viewport = { themeColor: "#1E40AF", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
