import { auth } from "@/lib/auth"
import { NextResponse } from "next/server"

export const proxy = auth((req) => {
  const isLoggedIn = !!req.auth
  const isLoginPage = req.nextUrl.pathname === "/login"

  if (!isLoggedIn && !isLoginPage) {
    return NextResponse.redirect(new URL("/login", req.url))
  }

  if (isLoggedIn && isLoginPage) {
    return NextResponse.redirect(new URL("/", req.url))
  }

  return NextResponse.next()
})

export const config = {
  matcher: [
    // Exclude api/auth (OAuth callbacks), static files, image optimization, favicon
    "/((?!api/auth|_next/static|_next/image|favicon.ico).*)",
  ],
}
