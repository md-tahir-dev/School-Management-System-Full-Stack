import "@fontsource-variable/figtree";
import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "School Management System", template: "%s | School Management System" },
  description: "Students, teachers, fees, results and more in one place.",
};

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
