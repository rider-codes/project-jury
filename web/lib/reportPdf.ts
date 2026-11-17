/** The review as a short PDF that looks like the site: the same light Cobalt colours, cards with a
 *  hard outline and offset shadow, stance pills, and each reviewer's portrait on their tile colour.
 *  Built in the browser with jsPDF (loaded only when someone downloads), as real text, not a picture. */
import type { jsPDF as JsPDF } from "jspdf";
import type { RoomState } from "./room";
import type { Stance } from "./types";

type Names = Record<string, string>;
type RGB = [number, number, number];
/** PNG data URLs by key: "logo" and one per persona id. Missing ones are simply left out. */
export type ReportImages = Record<string, string>;

const hex = (h: string): RGB => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];

// the site's light theme (app/showcase-theme.css)
const C = {
  bg: hex("#f1f3f6"), panel: hex("#ffffff"), panel2: hex("#f6f8fb"), line: hex("#d9dee6"), line2: hex("#c3cad6"),
  text: hex("#151c28"), text3: hex("#3a4558"), muted: hex("#566073"), accent: hex("#2447d6"), accentBg: hex("#e6ecfd"),
  hi: hex("#ffe14d"), edge: hex("#151c28"),
};
const STANCE: Record<Stance, { color: RGB; answer: string }> = {
  useful: { color: hex("#1b7a4b"), answer: "Yes" },
  unsure: { color: hex("#9a6200"), answer: "Not sure yet" },
  "not useful": { color: hex("#bb3a2c"), answer: "No" },
};
const TILE: Record<string, RGB> = {
  senior_engineer: hex("#d3e0ff"), product_manager: hex("#ffe2bf"), ux_designer: hex("#f8d4e4"),
  general_user: hex("#cdeedb"), hiring_manager: hex("#e1d8fb"), open_source_maintainer: hex("#f6e7b3"),
};
const STANCES: Stance[] = ["useful", "unsure", "not useful"];

export function fileName(room: RoomState, ext: string): string {
  const slug = (room.project?.name ?? "project").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return `${slug || "project"}-jury-report.${ext}`;
}

/** The built-in PDF fonts cover Latin-1 only; swap common typography for plain equivalents. */
function plain(s: string): string {
  return s
    .replace(/[‘’]/g, "'").replace(/[“”]/g, '"')
    .replace(/[–—]/g, "-").replace(/…/g, "...").replace(/×/g, "x").replace(/→/g, "->")
    .replace(/[^\x09\x0A\x0D\x20-\x7E\xA0-\xFF]/g, "?");
}

/** The gist of a long point: the part before the first ":", " - " or ";", cut to about 90 characters. */
function gist(text: string, max = 90): string {
  const t = text.trim();
  const cut = t.search(/: | — | – | - |; /);
  const g = cut >= 40 ? t.slice(0, cut) : t;
  if (g.length > max) return g.slice(0, g.lastIndexOf(" ", max)).replace(/[.,;:]$/, "") + "...";
  return g.replace(/[.,]$/, "");
}

/** Lay the review out on the page. Split from saving so it can be built and checked outside a browser. */
export async function buildPdf(room: RoomState, names: Names, questions: Record<string, string> = {},
                               images: ReportImages = {}): Promise<JsPDF | null> {
  if (!room.project) return null;
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const W = doc.internal.pageSize.getWidth();
  const H = doc.internal.pageSize.getHeight();
  const M = 40;
  const IW = W - 2 * M; // inner width
  let y = 0;
  const name = (id: string) => names[id] ?? id;

  const paintPage = () => {
    doc.setFillColor(...C.bg);
    doc.rect(0, 0, W, H, "F");
  };
  const newPage = () => { doc.addPage(); paintPage(); y = M; };
  const fits = (h: number) => { if (y + h > H - M - 16) newPage(); };

  const font = (size: number, bold = false, color: RGB = C.text, face = "helvetica") => {
    doc.setFont(face, bold ? "bold" : "normal");
    doc.setFontSize(size);
    doc.setTextColor(...color);
  };
  const wrap = (s: string, size: number, width: number, bold = false): string[] => {
    font(size, bold);
    return doc.splitTextToSize(plain(s), width) as string[];
  };
  const lh = (size: number) => size * 1.38;

  /** A card like the site's: white, rounded, outlined, with a flat offset shadow when `strong`. */
  const card = (x: number, top: number, w: number, h: number, strong = false) => {
    if (strong) {
      doc.setFillColor(...C.edge);
      doc.roundedRect(x + 4, top + 4, w, h, 12, 12, "F");
    }
    doc.setFillColor(...C.panel);
    doc.setDrawColor(...(strong ? C.edge : C.line2));
    doc.setLineWidth(strong ? 2 : 1);
    doc.roundedRect(x, top, w, h, 12, 12, "FD");
  };
  /** An outlined pill, like the stance badges on the site. Returns its width. */
  const pill = (x: number, top: number, label: string, color: RGB, size = 9.5): number => {
    font(size, true, color);
    const w = doc.getTextWidth(plain(label)) + 18;
    doc.setDrawColor(...color);
    doc.setLineWidth(1.2);
    doc.setFillColor(...C.panel);
    doc.roundedRect(x, top, w, size + 10, (size + 10) / 2, (size + 10) / 2, "FD");
    doc.text(plain(label), x + 9, top + size + 3.5);
    return w;
  };
  const kicker = (s: string, x: number, top: number) => {
    font(8, true, C.accent);
    doc.setCharSpace(0.9);
    doc.text(s.toUpperCase(), x, top);
    doc.setCharSpace(0);
  };

  // ---------- first page: header and title ----------
  paintPage();
  y = M;
  if (images.logo) doc.addImage(images.logo, "PNG", M, y - 4, 26, 26);
  font(14, true);
  doc.text("Project Jury", M + (images.logo ? 34 : 0), y + 14);
  font(9, false, C.muted);
  doc.text(`Review report  -  ${new Date().toISOString().slice(0, 10)}`, W - M, y + 14, { align: "right" });
  y += 46;

  // "Is <name> useful?" with the site's yellow highlighter under "useful"
  const p = room.project;
  const titleSize = 26;
  const before = `Is ${plain(p.name)} `;
  const titleLines = wrap(`${before}useful?`, titleSize, IW, true);
  font(titleSize, true);
  if (titleLines.length === 1) {
    const x0 = M + doc.getTextWidth(before);
    const wU = doc.getTextWidth("useful");
    doc.setFillColor(...C.hi);
    doc.rect(x0 - 2, y + titleSize * 0.55, wU + 4, titleSize * 0.42, "F");
    font(titleSize, true);
    doc.text(titleLines[0], M, y + titleSize);
    y += lh(titleSize);
  } else {
    for (const l of titleLines) { doc.text(l, M, y + titleSize); y += lh(titleSize); }
  }
  const src = [p.files ? `${p.files} files read` : "live site only", p.demo_steps ? `${p.demo_steps} demo steps` : "no demo",
    p.site_views ? `${p.site_views} live site views` : ""].filter(Boolean).join("   |   ");
  for (const l of wrap(`${p.repo_url}   |   ${src}`, 9.5, IW)) { font(9.5, false, C.muted); doc.text(l, M, y + 10); y += lh(9.5); }
  y += 6;
  const n = room.verdicts.length || room.personaIds.length;
  for (const l of wrap(`${n} AI reviewer${n === 1 ? "" : "s"} read this project. Each answered one question from their own point of view. Here is what they decided, and what they would change.`, 11, IW)) {
    font(11, false, C.text3); doc.text(l, M, y + 11); y += lh(11);
  }
  y += 16;

  // ---------- the verdict card ----------
  if (room.summary) {
    const s = room.summary;
    const P = 20; // card padding
    const headLines = wrap(s.headline, 14, IW - 2 * P, true);
    const changes = s.top_changes.slice(0, 3).map((t) => wrap(gist(t), 10.5, IW - 2 * P - 26));
    const h = P + 12 + 12 + 28 + headLines.length * lh(14) + (changes.length ? 22 + changes.reduce((a, c) => a + c.length * lh(10.5) + 8, 0) : 0) + P - 4;
    fits(h + 8);
    const top = y;
    card(M, top, IW, h, true);
    let cy = top + P + 8;
    kicker("The verdict", M + P, cy);
    cy += 12;
    let px = M + P;
    for (const st of STANCES) {
      const k = s.tally[st];
      if (!k) continue;
      px += pill(px, cy, `${k}  ${STANCE[st].answer}`, STANCE[st].color) + 8;
    }
    cy += 32;
    for (const l of headLines) { font(14, true); doc.text(l, M + P, cy + 12); cy += lh(14); }
    if (changes.length) {
      cy += 10;
      font(10.5, true, C.text);
      doc.text("What to change first", M + P, cy + 9);
      cy += 18;
      changes.forEach((lines, i) => {
        doc.setFillColor(...C.accent);
        doc.circle(M + P + 8, cy + 6, 8, "F");
        font(9, true, C.panel);
        doc.text(String(i + 1), M + P + 8, cy + 9.2, { align: "center" });
        for (const l of lines) { font(10.5, false, C.text3); doc.text(l, M + P + 26, cy + 10); cy += lh(10.5); }
        cy += 8;
      });
    }
    y = top + h + 22;
  }

  // ---------- one card per reviewer ----------
  if (room.verdicts.length) {
    fits(60);
    font(16, true);
    doc.text("What each reviewer said", M, y + 14);
    y += 30;
    const P = 16;
    const AV = 52; // portrait tile
    const TX = M + P + AV + 14; // text column
    const TW = W - M - P - TX;
    for (const v of room.verdicts) {
      const st = STANCE[v.verdict];
      const q = questions[v.persona_id];
      const qLines = q ? wrap(`"${q}"`, 9.5, TW - 110) : [];
      const head = wrap(v.headline, 11.5, TW, true);
      const why = v.reasons.slice(0, 2).map((r) => wrap(gist(r.text), 9.5, TW - 12));
      const change = v.what_would_change_my_mind.length ? wrap(gist(v.what_would_change_my_mind[0]), 9.5, TW - 12) : [];
      const textH = 16 + qLines.length * lh(9.5) + 8 + head.length * lh(11.5) + 6
        + (why.length ? 14 + why.reduce((a, l) => a + l.length * lh(9.5) + 2, 0) : 0)
        + (change.length ? 16 + change.length * lh(9.5) : 0);
      const h = Math.max(AV + 2 * P, textH + 2 * P);
      fits(h + 12);
      const top = y;
      card(M, top, IW, h);

      // portrait on its tile colour, as on the site
      doc.setFillColor(...(TILE[v.persona_id] ?? C.accentBg));
      doc.roundedRect(M + P, top + P, AV, AV, 10, 10, "F");
      if (images[v.persona_id]) doc.addImage(images[v.persona_id], "PNG", M + P + 2, top + P + 2, AV - 4, AV - 4);

      let cy = top + P;
      font(12.5, true);
      doc.text(plain(name(v.persona_id)), TX, cy + 12);
      const pw = (() => { font(9.5, true); return doc.getTextWidth(st.answer) + 18; })();
      pill(W - M - P - pw, cy, st.answer, st.color);
      cy += 16;
      for (const l of qLines) { font(9.5, false, C.muted); doc.text(l, TX, cy + 9); cy += lh(9.5); }
      cy += 8;
      for (const l of head) { font(11.5, true, C.text); doc.text(l, TX, cy + 11); cy += lh(11.5); }
      cy += 6;
      if (why.length) {
        kicker("Why", TX, cy + 8);
        cy += 14;
        for (const lines of why) {
          doc.setFillColor(...C.line2);
          doc.rect(TX, cy + 1, 2, lines.length * lh(9.5) - 3, "F");
          for (const l of lines) { font(9.5, false, C.text3); doc.text(l, TX + 10, cy + 9); cy += lh(9.5); }
          cy += 2;
        }
      }
      if (change.length) {
        cy += 6;
        kicker("To change their mind", TX, cy + 8);
        cy += 10;
        for (const l of change) { font(9.5, false, C.text3); doc.text(l, TX, cy + 9); cy += lh(9.5); }
      }
      y = top + h + 12;
    }
  }

  // closing note, then a footer on every page
  y += 8;
  fits(30);
  for (const l of wrap("Every point is backed by a quote that code checked against the project. The full review, with every quote, the debate and your answers, is in the app.", 9, IW)) {
    font(9, false, C.muted); doc.text(l, M, y + 9); y += lh(9);
  }
  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    doc.setDrawColor(...C.line);
    doc.setLineWidth(0.8);
    doc.line(M, H - 30, W - M, H - 30);
    font(8.5, false, C.muted);
    doc.text(`Project Jury  -  ${plain(p.name)}`, M, H - 17);
    doc.text(`${i} / ${pages}`, W - M, H - 17, { align: "right" });
  }
  return doc;
}

/** A same-site image as a PNG data URL (SVGs are drawn onto a canvas first). Null if it cannot load. */
async function loadPng(src: string, size = 256): Promise<string | null> {
  try {
    const img = new Image();
    img.decoding = "async";
    img.src = src;
    await img.decode();
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = Math.round(size * (img.naturalHeight / img.naturalWidth || 1));
    canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/png");
  } catch {
    return null;
  }
}

export async function downloadPdf(room: RoomState, names: Names, questions: Record<string, string> = {}): Promise<void> {
  const ids = room.verdicts.map((v) => v.persona_id);
  const loaded = await Promise.all([
    loadPng("/brand/logo-mark.svg", 128).then((d) => ["logo", d] as const),
    ...ids.map((id) => loadPng(`/personas/${id}.png`, 160).then((d) => [id, d] as const)),
  ]);
  const images: ReportImages = Object.fromEntries(loaded.filter(([, d]) => d) as [string, string][]);
  const doc = await buildPdf(room, names, questions, images);
  doc?.save(fileName(room, "pdf"));
}
