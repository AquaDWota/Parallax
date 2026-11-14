/** Proxies /api/* to the FastAPI backend so the browser talks to one origin. */
// 127.0.0.1, not localhost: on macOS Node resolves localhost to ::1 (IPv6) but uvicorn binds IPv4.
const API = process.env.PARALLAX_API_URL || "http://127.0.0.1:8000";
export default {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};
