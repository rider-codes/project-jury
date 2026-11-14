"use client";

/** Illustrations for the public showcase. Pure HTML/CSS/SVG, drawn from real persona data. */
import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { accent, portrait, STANCE_COLOR } from "@/lib/personas";
import type { Persona, Stance } from "@/lib/types";

const acc = (id: string) => ({ "--accent": accent(id) }) as CSSProperties;

/* ---------- Hero: the jury seated in an arc around your project ---------- */

const ANGLES = [165, 135, 105, 75, 45, 15]; // seat angles on the arc, left to right
const BOTTOM_GAP = 28; // room between the project card and the bottom of the window
const MIN_H = 300; // shorter than this the rings crowd; on very short screens the page scrolls instead
const MAX_TALL = 1 / 1.55; // never taller than this share of the width
const CARD_H = 118; // the project card's rendered height (bar + two rows of files)

type Box = { w: number; h: number };

/** Every position in the art, in pixels, from the box the art actually has. A wide, short
 *  box gives a wide, flat arc; a narrower one a rounder arc. The lines always land on the card. */
function layout({ w, h }: Box) {
  const s = Math.max(0.6, Math.min(1.3, h / 500)); // ring and label scale (grows a little on tall screens)
  const ring = 92 * s;
  const cardW = Math.max(240, Math.min(360, w * 0.24));
  const cardTop = h - CARD_H - 4;
  const cx = w / 2;
  const cy = cardTop + CARD_H * 0.45; // arc centre sits inside the card, so the outer seats flank it
  const topRoom = ring / 2 + 40 * s; // keeps the top seats' bubbles inside the box
  const ry = (cy - topRoom) / Math.sin((105 * Math.PI) / 180);
  const labelHalf = 105 * Math.max(s, 0.85); // half the widest name ("Open-source maintainer")
  const rx = Math.max(ry, w / 2 - labelHalf);
  const seats = ANGLES.map((deg) => {
    const r = (deg * Math.PI) / 180;
    return { x: cx + rx * Math.cos(r), y: cy - ry * Math.sin(r) };
  });
  const spread = (cardW * 0.72) / (ANGLES.length - 1);
  const landing = seats.map((_, i) => ({ x: cx + (i - (ANGLES.length - 1) / 2) * spread, y: cardTop + 8 }));
  return { s, cardW, cardTop, seats, landing };
}

/** Size the art so the whole hero (copy, jury arc and project card) fits in the first screen,
 *  using the full width of the column on big screens. */
function useFitToScreen() {
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<Box | null>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fit = () => {
      if (window.innerWidth <= 720) { setBox(null); return; } // phone layout is a simple grid
      const top = el.getBoundingClientRect().top + window.scrollY;
      const room = window.innerHeight - top - BOTTOM_GAP;
      const w = el.parentElement?.clientWidth ?? 1000;
      setBox({ w, h: Math.round(Math.max(MIN_H, Math.min(room, w * MAX_TALL))) });
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);
  return { ref, box };
}

export function HeroArt({ personas }: { personas: Persona[] }) {
  const six = personas.slice(0, 6);
  const { ref, box } = useFitToScreen();
  const b = box ?? { w: 1000, h: 470 };
  const { s, cardW, cardTop, seats, landing } = layout(b);
  return (
    <div ref={ref} className="sc-hero" role="img" aria-label="Six AI reviewers seated in an arc, each examining your project"
         style={box ? ({ width: b.w, height: b.h, "--s": s } as CSSProperties) : undefined}>
      <svg className="sc-hero-lines" viewBox={`0 0 ${b.w} ${b.h}`} aria-hidden="true">
        {six.map((p, i) => (
          <line key={p.id} x1={seats[i].x} y1={seats[i].y} x2={landing[i].x} y2={landing[i].y}
                stroke={accent(p.id)} strokeWidth="2" vectorEffect="non-scaling-stroke"
                className="sc-signal" style={{ animationDelay: `${i * 0.35}s` }} />
        ))}
      </svg>

      {six.map((p, i) => (
        <div key={p.id} className="sc-seat" data-p={p.id} style={{ ...acc(p.id), left: seats[i].x, top: seats[i].y, animationDelay: `${i * 0.5}s` }}>
          <div className="sc-seat-ring"><img src={portrait(p.id)} alt="" width={84} height={94} /></div>
          <span className="sc-seat-name">{p.name}</span>
          <span className={`sc-bubble ${i < 3 ? "left" : "right"}`} style={{ animationDelay: `${0.8 + i * 0.9}s` }}>
            {p.verdict_question}
          </span>
        </div>
      ))}

      <div className="sc-project" style={{ left: b.w / 2, top: cardTop, width: cardW }}>
        <div className="sc-project-bar"><i /><i /><i /><span className="mono">github.com/you/project</span></div>
        <div className="sc-project-files mono">
          <span>README.md</span><span>src/app.py</span><span>tests/</span><span>demo: step-1…3</span>
        </div>
        <div className="sc-scan" aria-hidden="true" />
      </div>
    </div>
  );
}

/* ---------- How it works: four illustrated stages ---------- */

function Mini({ id }: { id: string }) {
  return <span className="sc-mini" data-p={id} style={acc(id)}><img src={portrait(id)} alt="" width={34} height={38} /></span>;
}

function Chip({ stance }: { stance: Stance }) {
  return <span className="sc-chip" style={{ color: STANCE_COLOR[stance] }}>{stance}</span>;
}

export function Pipeline() {
  return (
    <ol className="sc-flow">
      <li className="sc-stage">
        <div className="sc-art sc-art-read" aria-hidden="true">
          {["README.md", "src/app.py", "package.json", "demo step-2"].map((f, i) => (
            <span key={f} className="sc-file mono" style={{ animationDelay: `${i * 0.4}s` }}>{f}</span>
          ))}
          <span className="sc-brief mono">brief · 40 files max · secrets redacted</span>
        </div>
        <span className="label">Step 1</span>
        <h3>Read</h3>
        <p>Your public repo and a short walkthrough become one brief: key files, the full file list, and your demo steps.</p>
      </li>

      <li className="sc-stage">
        <div className="sc-art sc-art-first" aria-hidden="true">
          <div className="sc-row"><Mini id="senior_engineer" /><Chip stance="not useful" /></div>
          <div className="sc-row"><Mini id="product_manager" /><Chip stance="unsure" /></div>
          <div className="sc-row"><Mini id="ux_designer" /><Chip stance="useful" /></div>
          <div className="sc-merge mono"><span>?</span><span>?</span><span>?</span><b>→ 1 question for you</b></div>
        </div>
        <span className="label">Step 2</span>
        <h3>First impressions</h3>
        <p>Each reviewer judges alone. Duplicate questions merge into one card, and the room waits for your answer.</p>
      </li>

      <li className="sc-stage">
        <div className="sc-art sc-art-debate" aria-hidden="true">
          <div className="sc-say left" style={acc("product_manager")}><Mini id="product_manager" /><span>No user, no reason to switch.</span></div>
          <div className="sc-challenge mono">challenges ↓</div>
          <div className="sc-say right" style={acc("ux_designer")}><span>Then show one result in seconds.</span><Mini id="ux_designer" /></div>
          <div className="sc-mod mono">moderator · most challenged speaks next</div>
        </div>
        <span className="label">Step 3</span>
        <h3>Debate</h3>
        <p>A moderator written in code, not a model, picks who speaks. Changing a stance needs a stated reason.</p>
      </li>

      <li className="sc-stage">
        <div className="sc-art sc-art-verdict" aria-hidden="true">
          {([["useful", 3], ["unsure", 1], ["not useful", 0]] as [Stance, number][]).map(([s, n], i) => (
            <div key={s} className="sc-bar-row">
              <span className="mono" style={{ color: STANCE_COLOR[s] }}>{s}</span>
              <span className="sc-bar" style={{ "--w": `${n * 40}%`, background: STANCE_COLOR[s], animationDelay: `${i * 0.25}s` } as CSSProperties} />
            </div>
          ))}
          <div className="sc-change mono">✓ what would change my mind</div>
        </div>
        <span className="label">Step 4</span>
        <h3>Verdicts</h3>
        <p>Each reviewer answers their own question, with reasons and what would change their mind. Then a summary.</p>
      </li>
    </ol>
  );
}

/* ---------- The evidence rule, shown on real text ---------- */

export function EvidenceDemo() {
  return (
    <div className="sc-evidence">
      <div className="sc-ev-pair">
        <div className="sc-ev-claim" style={acc("senior_engineer")}>
          <div className="sc-ev-who"><Mini id="senior_engineer" /><span className="mono">Senior engineer claims</span></div>
          <p>&ldquo;One test runs the server out of file descriptors and checks it recovers.&rdquo;</p>
          <span className="mono sc-ev-cite">cites accept_resilience.rs</span>
        </div>
        <div className="sc-ev-arrow ok" aria-hidden="true"><span>quote found</span></div>
        <div className="sc-ev-file">
          <div className="sc-ev-file-head mono">packages/core/tests/accept_resilience.rs</div>
          <pre className="mono"><span className="ln">1</span>{"panic!(\""}<mark>the server stopped accepting after running out of descriptors</mark>{"\")"}</pre>
        </div>
        <div className="sc-ev-verdict ok">✓ kept</div>
      </div>

      <div className="sc-ev-pair">
        <div className="sc-ev-claim struck" style={acc("product_manager")}>
          <div className="sc-ev-who"><Mini id="product_manager" /><span className="mono">An invented claim</span></div>
          <p>&ldquo;CI runs the tests on every push.&rdquo;</p>
          <span className="mono sc-ev-cite">cites .github/workflows/ci.yml</span>
        </div>
        <div className="sc-ev-arrow bad" aria-hidden="true"><span>not in the repo</span></div>
        <div className="sc-ev-file missing">
          <div className="sc-ev-file-head mono">.github/workflows/ci.yml</div>
          <pre className="mono">file does not exist</pre>
        </div>
        <div className="sc-ev-verdict bad">✗ dropped</div>
      </div>
      <p className="evidence" style={{ margin: 0 }}>The first pair is from the recorded review below. The second is an illustration of what the checker throws out.</p>
    </div>
  );
}

/* ---------- Numbers from the recorded run ---------- */

export function StatsBand({ items }: { items: [string, string][] }) {
  return (
    <div className="sc-stats">
      {items.map(([n, label]) => (
        <div key={label} className="sc-stat"><span className="sc-stat-n">{n}</span><span className="sc-stat-l">{label}</span></div>
      ))}
    </div>
  );
}

/* ---------- Ticker tape of real findings from the recorded review ---------- */

export function Ticker({ items }: { items: string[] }) {
  if (!items.length) return null;
  const row = (suffix: string) =>
    items.map((t, i) => (
      <span key={`${suffix}${i}`} className="sc-tick">
        <b aria-hidden="true">&#9670;</b> {t}
      </span>
    ));
  return (
    <div className="sc-ticker" role="region" aria-label="Findings from the recorded review">
      <div className="sc-ticker-track">
        <div className="sc-ticker-row">{row("a")}</div>
        <div className="sc-ticker-row" aria-hidden="true">{row("b")}</div>
      </div>
    </div>
  );
}
