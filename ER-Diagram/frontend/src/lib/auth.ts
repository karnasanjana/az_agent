import NextAuth from "next-auth"
import Google from "next-auth/providers/google"

async function refreshAccessToken(token: any) {
  try {
    const response = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: process.env.AUTH_GOOGLE_ID!,
        client_secret: process.env.AUTH_GOOGLE_SECRET!,
        grant_type: "refresh_token",
        refresh_token: token.refreshToken as string,
      }),
    })

    const refreshed = await response.json()

    if (!response.ok) {
      throw new Error(refreshed.error || "Failed to refresh token")
    }

    return {
      ...token,
      accessToken: refreshed.access_token,
      // Google returns expires_in (seconds from now)
      expiresAt: Math.floor(Date.now() / 1000) + refreshed.expires_in,
      // Google may rotate the refresh token — use new one if provided
      refreshToken: refreshed.refresh_token ?? token.refreshToken,
    }
  } catch (error) {
    console.error("Error refreshing access token:", error)
    return {
      ...token,
      error: "RefreshTokenError",
    }
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  // Production builds otherwise reject a non-Vercel host with UntrustedHost,
  // 500-ing /api/auth/session (dev trusts localhost automatically). Safe here:
  // the app runs behind a known host, not arbitrary public traffic.
  trustHost: true,
  providers: [
    Google({
      clientId: process.env.AUTH_GOOGLE_ID,
      clientSecret: process.env.AUTH_GOOGLE_SECRET,
      authorization: {
        url: "https://accounts.google.com/o/oauth2/auth",
        params: {
          scope: "openid email profile https://www.googleapis.com/auth/bigquery https://www.googleapis.com/auth/devstorage.read_only",
          access_type: "offline",
          prompt: "consent",
          response_type: "code",
        },
      },
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      // First login — save access token, refresh token, and expiry
      if (account) {
        return {
          ...token,
          accessToken: account.access_token,
          refreshToken: account.refresh_token,
          expiresAt: account.expires_at, // Unix timestamp (seconds)
        }
      }

      // Token not expired yet — return as-is
      const expiresAt = token.expiresAt as number
      if (Date.now() < expiresAt * 1000) {
        return token
      }

      // Token expired — refresh it
      return await refreshAccessToken(token)
    },
    async session({ session, token }) {
      if (token.sub) {
        session.user.id = token.sub
      }
      (session as any).accessToken = token.accessToken

      // Pass refresh error to client so it can trigger re-login
      if (token.error) {
        (session as any).error = token.error
      }

      return session
    },
  },
  pages: {
    signIn: "/login",
  },
})
