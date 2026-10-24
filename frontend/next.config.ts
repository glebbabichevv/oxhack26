import path from "node:path";
import type { NextConfig } from "next";

// Pin the root: there is a stray package-lock.json in the user's home folder.
const nextConfig: NextConfig = { outputFileTracingRoot: path.join(__dirname) };

export default nextConfig;
