import { redirect } from "next/navigation";

// middleware.ts normally redirects "/" first; this is the fallback.
export default function Home() {
  redirect("/login");
}
