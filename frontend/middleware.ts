import { NextResponse, type NextRequest } from "next/server";

const ROLES = ["ceo", "admin", "teacher", "student", "parent"];

/**
 * Route gating by role, using the `sms_role` cookie the API sets at sign-in.
 *
 * This is a UX guard only: the cookie is not signed and is readable by the user. It stops people
 * wandering into another role's screens; every real permission check happens in the FastAPI backend,
 * which trusts only the signed access token and the role stored in the database.
 */
export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const roleCookie = req.cookies.get("sms_role")?.value;
  const role = roleCookie && ROLES.includes(roleCookie) ? roleCookie : null;
  const first = pathname.split("/")[1] ?? "";

  if (pathname === "/") {
    return NextResponse.redirect(new URL(role ? `/${role}` : "/login", req.url));
  }

  if (pathname === "/change-password" && !role) {
    return NextResponse.redirect(new URL("/login", req.url));
  }

  if (ROLES.includes(first)) {
    if (!role) {
      const url = new URL("/login", req.url);
      url.searchParams.set("next", pathname);
      return NextResponse.redirect(url);
    }
    if (first !== role) {
      return NextResponse.redirect(new URL(`/${role}`, req.url));
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|api/|favicon.ico|.*\\..*).*)"],
};
