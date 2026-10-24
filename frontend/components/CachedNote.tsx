"use client";

import { useEffect, useState } from "react";
import { cachedAt, hhmm, onCacheChange } from "@/lib/api";

/** A small grey line when some of this page's data is the offline copy (venue Wi-Fi). */
export function CachedNote({ paths, className }: { paths: string[]; className?: string }) {
  const [, tick] = useState(0);
  useEffect(() => onCacheChange(() => tick((x) => x + 1)), []);
  const t = cachedAt(paths);
  if (t === undefined) return null;
  return <p className={`text-[12px] text-ink-faint tabular-nums ${className ?? ""}`}>Offline copy · cached at {hhmm(t)}</p>;
}
