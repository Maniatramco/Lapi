/* The 1-minute Lapi tour: scene script and pure timing helpers (no React, unit tested). */

export type SceneId = "welcome" | "connect" | "unify" | "ask" | "extract" | "skills" | "secure";
export type Scene = { id: SceneId; title: string; caption: string; seconds: number };

/** Raise when the tour changes enough to show it again; must match the API's TOUR_VERSION. */
export const TOUR_VERSION = 3;

/** Each caption is also the scene's voice-over line, so subtitles always match the narration.
 * Keep lines short enough to speak within the scene (see `wordsPerSecond`). Two versions share
 * the scene ids and timing: a computer (web) one and a phone one. */
export type Device = "desktop" | "mobile";

export const SCENES: readonly Scene[] = [
  { id: "welcome", title: "Welcome", seconds: 7,
    caption: "Welcome to Lapi. Connect your knowledge, unify it in one place, and ask it anything." },
  { id: "connect", title: "Connect", seconds: 10,
    caption: "Use Add knowledge to upload files, or connect cloud storage, Google Drive and SharePoint. A step-by-step guide helps with each one." },
  { id: "unify", title: "Unify", seconds: 12,
    caption: "Documents go into datasets. Lapi reads them, even scans and photos, and indexes them with the models your administrator chose." },
  { id: "ask", title: "Ask", seconds: 12,
    caption: "Ask the Lapi Agent in plain language. Every answer shows its sources. Press the question mark key to see keyboard shortcuts." },
  { id: "extract", title: "Extract & review", seconds: 10,
    caption: "Need data out? Lapi suggests the fields, then you review each value side by side with its source." },
  { id: "skills", title: "Skills", seconds: 9,
    caption: "Teach the agent with skills: a short playbook for a kind of document, written or uploaded once. It uses them whenever they fit." },
  { id: "secure", title: "Secure by design", seconds: 9,
    caption: "Single sign-on, access per dataset and an activity log keep it safe. You're ready: start with Quick start on your Dashboard." },
];

export const MOBILE_SCENES: readonly Scene[] = [
  { id: "welcome", title: "Welcome", seconds: 7,
    caption: "Welcome to Lapi on your phone. Bring in documents and ask them anything, in a few taps." },
  { id: "connect", title: "Add", seconds: 10,
    caption: "Tap Add at the bottom. Take a photo of a paper document, or pick files. Several pages can be merged into one." },
  { id: "unify", title: "Read", seconds: 12,
    caption: "Lapi reads every page, even photos and scans, and keeps them in your dataset, using the models your administrator chose." },
  { id: "ask", title: "Ask", seconds: 12,
    caption: "Ask in plain language, right from your phone. Every answer shows its sources, so you can check them." },
  { id: "extract", title: "Extract", seconds: 10,
    caption: "Pull out data in Quick start: Lapi suggests the fields, extracts them, and you review each value." },
  { id: "skills", title: "Skills", seconds: 9,
    caption: "Skills teach the agent how to handle a kind of document. Add one once, and it is used whenever it fits." },
  { id: "secure", title: "Secure", seconds: 9,
    caption: "Sign in once, see only what is shared with you, and every change is logged. Start with Quick start." },
];

export const scenesFor = (device: Device): readonly Scene[] => device === "mobile" ? MOBILE_SCENES : SCENES;
/** Phones get the phone version: narrow screens, as the app's own phone layout uses. */
export const MOBILE_QUERY = "(max-width: 640px)";

/** Spoken words per second a scene's line needs; narration at a normal pace is about 2.5 to 3. */
export function wordsPerSecond(scene: Scene): number {
  return scene.caption.split(/\s+/).filter(Boolean).length / scene.seconds;
}

type VoiceLike = { name: string; lang: string; localService?: boolean };
/** The most natural English voice the device offers (names differ per browser and phone). */
export function pickVoice<T extends VoiceLike>(voices: readonly T[]): T | undefined {
  const score = (voice: T) => (/natural|neural/i.test(voice.name) ? 8 : 0) + (/google/i.test(voice.name) ? 4 : 0)
    + (/samantha|aria|jenny|guy|libby|sonia|daniel|karen/i.test(voice.name) ? 3 : 0)
    + (/^en[-_](us|gb|in|au)/i.test(voice.lang) ? 2 : 0) + (voice.localService === false ? 1 : 0);
  return voices.filter(voice => /^en/i.test(voice.lang)).sort((a, b) => score(b) - score(a))[0];
}

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
