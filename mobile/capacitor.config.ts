import type { CapacitorConfig } from "@capacitor/cli"

// Thin shell, Home-Assistant style: one universal app, not one build per
// instance. The bundled www/ onboarding screen asks for an OpenHost-hosted
// Sculptor URL on first launch, persists it, and navigates the WebView there.
// Nothing instance-specific is baked in at build time.
//
// `allowNavigation: ["*"]` is load-bearing: without it Capacitor treats the
// remote instance as an "external" host and bounces it to the system browser
// instead of loading it inside the app WebView. Because the user points the app
// at their own server, allowing the WebView to navigate anywhere is acceptable
// here — links the remote UI can't reach in-app would otherwise break.
//
// Loading the live UI over its own origin keeps every API/WebSocket call
// same-origin, so the backend's localhost-only CORS allow-list never applies,
// and Sculptor's web-mode session cookie self-bootstraps from the SPA as usual.
const config: CapacitorConfig = {
  appId: "com.imbue.sculptor",
  appName: "Sculptor",
  webDir: "www",
  server: {
    androidScheme: "https",
    allowNavigation: ["*"],
  },
}

export default config
