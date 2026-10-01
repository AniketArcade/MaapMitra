import { NextResponse, type NextRequest } from "next/server";

// Coarse UX guard: no session flag cookie on a private route -> /login.
// lm_session carries no secret; the backend enforces every permission.
export function proxy(request: NextRequest) {
  if (request.cookies.has("lm_session")) return NextResponse.next();
  const login = new URL("/login", request.url);
  login.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search);
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except "/", public pages, the API rewrite, Next internals and static files.
  matcher: [
    "/((?!api|_next/static|_next/image|verify|login|register|official-login|how-it-works|support|favicon.ico|.*\\..*).+)",
  ],
};
