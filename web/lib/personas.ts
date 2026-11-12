import type { Stance } from "./types";

/** One accent per persona, from the design canvas. */
export const ACCENT: Record<string, string> = {
  senior_engineer: "#7DD3FC",
  product_manager: "#FDBA74",
  ux_designer: "#F9A8D4",
  general_user: "#6EE7B7",
  hiring_manager: "#C4B5FD",
  open_source_maintainer: "#FCD34D",
};

export const accent = (id: string) => ACCENT[id] ?? "#A6B0CC";

export const STANCE_COLOR: Record<Stance, string> = {
  useful: "#86EFAC",
  unsure: "#FCD34D",
  "not useful": "#FCA5A5",
};

export const STANCE_LABEL: Record<Stance, string> = {
  useful: "Useful",
  unsure: "Unsure",
  "not useful": "Not useful",
};

export const portrait = (id: string) => `/personas/${id}.png`;
