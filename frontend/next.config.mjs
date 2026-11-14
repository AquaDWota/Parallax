/** Proxies /api/* to the FastAPI backend so the browser talks to one origin. */
const API = process.env.PARALLAX_API_URL || "http://localhost:8000";
export default {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};
