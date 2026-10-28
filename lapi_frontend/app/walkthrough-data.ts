/* The 1-minute Lapi tour: scene script and pure timing helpers (no React, unit tested). */

export type SceneId = "welcome" | "connect" | "unify" | "ask" | "extract" | "secure";
export type Scene = { id: SceneId; title: string; caption: string; seconds: number };

/** Raise when the tour changes enough to show it again; must match the API's TOUR_VERSION. */
export const TOUR_VERSION = 1;

export const SCENES: readonly Scene[] = [
  { id: "welcome", title: "Welcome", seconds: 7,
    caption: "Connect. Unify. Ask. Lapi brings your documents, databases and apps into one knowledge base." },
  { id: "connect", title: "Connect", seconds: 10,
    caption: "Use Add knowledge to upload files or connect cloud storage, Google Drive and SharePoint, with a step-by-step guide for every connector." },
  { id: "unify", title: "Unify", seconds: 12,
    caption: "Documents land in datasets and are indexed, with OCR for scans and images. Each dataset picks its own Chat, Extraction, Embedding and OCR models." },
  { id: "ask", title: "Ask", seconds: 12,
    caption: "Ask the Lapi Agent in plain language. Every answer shows its sources, so you can check them." },
  { id: "extract", title: "Extract & review", seconds: 10,
    caption: "Prompt templates pull fields out of documents. Review them side by side with the source before the results are trusted." },
  { id: "secure", title: "Secure by design", seconds: 9,
    caption: "Single sign-on, access per dataset and an activity audit keep knowledge safe. You're ready: start on your Dashboard." },
];

export function totalSeconds(scenes: readonly Scene[] = SCENES): number {
  return scenes.reduce((sum, scene) => sum + scene.seconds, 0);
}

export function clampScene(index: number, scenes: readonly Scene[] = SCENES): number {
  if (!Number.isFinite(index) || scenes.length === 0) return 0;
  return Math.min(scenes.length - 1, Math.max(0, Math.trunc(index)));
}

export const nextScene = (index: number, scenes: readonly Scene[] = SCENES) => clampScene(index + 1, scenes);
export const previousScene = (index: number, scenes: readonly Scene[] = SCENES) => clampScene(index - 1, scenes);

/** Seconds from the start of the tour to the start of a scene. */
export function sceneStart(index: number, scenes: readonly Scene[] = SCENES): number {
  return scenes.slice(0, clampScene(index, scenes)).reduce((sum, scene) => sum + scene.seconds, 0);
}

/** The scene playing at a moment of the tour, and how far into it (both clamped to the tour). */
export function sceneAt(seconds: number, scenes: readonly Scene[] = SCENES): { index: number; offset: number; progress: number } {
  const total = totalSeconds(scenes);
  const t = Math.min(total, Math.max(0, Number.isFinite(seconds) ? seconds : 0));
  let start = 0;
  for (let index = 0; index < scenes.length; index++) {
    const length = scenes[index].seconds;
    if (t < start + length || index === scenes.length - 1) {
      const offset = Math.min(length, t - start);
      return { index, offset, progress: length ? offset / length : 1 };
    }
    start += length;
  }
  return { index: 0, offset: 0, progress: 0 };
}

/** How full each progress segment is (0..1) at a moment of the tour. */
export function segmentFill(seconds: number, scenes: readonly Scene[] = SCENES): number[] {
  const { index, progress } = sceneAt(seconds, scenes);
  return scenes.map((_, i) => (i < index ? 1 : i > index ? 0 : progress));
}

/** "m:ss" for the elapsed / total read-out. */
export function formatClock(seconds: number): string {
  const whole = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/** Show the first-login tour only when the server says this user has not seen the current version. */
export function shouldShowTour(status: unknown): boolean {
  if (!status || typeof status !== "object") return false;
  const { seen } = status as { seen?: unknown };
  return seen === false;
}
