/** A finished review as one file the builder can keep or send: Markdown, or a standalone HTML page
 *  that prints cleanly. Built in the browser from what is on screen, so it survives the host
 *  losing its history. */
import type { RoomState } from "./room";
import type { Claim, Stance } from "./types";

type Names = Record<string, string>;

const STANCES: Stance[] = ["useful", "unsure", "not useful"];

function evidence(c: Claim): string {
  const e = c.evidence;
  if (e.kind === "tree") return `repo tree: ${e.ref === "absent" ? "no file matching" : "has"} ${e.quote}`;
  const where = e.kind === "demo" ? `demo ${e.ref}` : e.kind === "site" ? `live site ${e.ref}`
    : e.kind === "answer" ? `the builder said (${e.ref})` : e.ref;
  return `${where}: "${e.quote}"`;
}

function sources(room: RoomState): string {
  const p = room.project!;
  return [`${p.files} files read`, p.demo_steps ? `${p.demo_steps} demo steps` : "no demo",
          p.site_views ? `${p.site_views} live site views (${p.site_url})` : ""].filter(Boolean).join(" · ");
}

const tallyLine = (room: RoomState) =>
  STANCES.filter((s) => room.summary?.tally[s]).map((s) => `${room.summary!.tally[s]} ${s}`).join(", ");

const dropped = (n: number) => (n ? `${n} claim${n > 1 ? "s" : ""} dropped: the evidence was not in the project` : "");

export function fileName(room: RoomState, ext: string): string {
  const slug = (room.project?.name ?? "project").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return `${slug || "project"}-jury-report.${ext}`;
}

export function reportMarkdown(room: RoomState, names: Names): string {
  if (!room.project) return "";
  const name = (id: string) => names[id] ?? id;
  const claims = (cs: Claim[]) => cs.map((c) => `- ${c.text}\n  - Evidence: ${evidence(c)}`);
  const out: string[] = [
    `# Project Jury review: ${room.project.name}`, "",
    `${room.project.repo_url}  `, sources(room), "",
  ];
  if (room.summary) {
    out.push("## Final summary", "", `**${room.summary.headline}** (${tallyLine(room)})`, "");
    for (const [label, items] of [["Agreed", room.summary.agreed], ["Split", room.summary.split],
                                  ["Top changes", room.summary.top_changes]] as const) {
      if (items.length) out.push(`### ${label}`, "", ...items.map((t) => `- ${t}`), "");
    }
  }
  if (room.verdicts.length) {
    out.push("## Final verdicts", "");
    for (const v of room.verdicts) {
      out.push(`### The ${name(v.persona_id)}: ${v.verdict}`, "", v.headline, "", ...claims(v.reasons));
      if (v.rejected.length) out.push(`- _${dropped(v.rejected.length)}_`);
      if (v.what_would_change_my_mind.length)
        out.push("", "What would change my mind:", ...v.what_would_change_my_mind.map((w) => `- ${w}`));
      out.push("");
    }
  }
  if (room.impressions.length) {
    out.push("## Round 1: first impressions", "");
    for (const i of room.impressions)
      out.push(`### The ${name(i.persona_id)}: ${i.stance}`, "", i.headline, "", ...claims(i.claims), "");
  }
  if (room.answered.length) {
    out.push("## Questions to the builder", "");
    for (const a of room.answered) out.push(`- **${a.question.text}**  \n  ${a.answer || "_Skipped_"}`);
    out.push("");
  }
  const turns = room.feed.flatMap((f) => (f.kind === "turn" && !f.turn.error ? [f.turn] : []));
  if (turns.length) {
    out.push("## Round 2: debate", "");
    for (const t of turns) {
      out.push(`**${name(t.speaker)}** (${t.stance})${t.contrarian ? " _arguing the other side_" : ""}: ${t.message}`);
      if (t.stance_changed) out.push(`  - Changed stance to ${t.stance}: ${t.stance_change_reason}`);
      out.push(...t.claims.map((c) => `  - ${c.text} (${evidence(c)})`), "");
    }
  }
  out.push("---", "Every claim above was checked by code against the repository, demo or live site. Claims whose quote could not be found were dropped.");
  return out.join("\n");
}

const esc = (s: string) => s.replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch]!);

const CSS = `
:root{--ink:#111827;--muted:#5b6475;--line:#e3e7ef;--bg:#fff;--soft:#f6f8fc;--accent:#1f5fd6}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:860px;margin:0 auto;padding:40px 20px 64px}
h1{font-size:30px;line-height:1.2;margin:0 0 8px}h2{font-size:20px;margin:40px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h3{font-size:16px;margin:0 0 6px}.meta{color:var(--muted);font-size:14px;overflow-wrap:anywhere}
.sum{background:var(--soft);border:1px solid var(--line);border-radius:12px;padding:20px;margin-top:24px}
.sum .head{font-size:19px;font-weight:700;margin:8px 0 12px}.sum h3{margin-top:14px;color:var(--muted);font-size:13px;text-transform:uppercase;letter-spacing:.06em}
.card{border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:12px 0;break-inside:avoid}
.tag{display:inline-block;font-size:12px;font-weight:700;border-radius:999px;padding:2px 10px;margin-left:8px;vertical-align:middle;border:1px solid}
.useful{color:#0f7a4a}.unsure{color:#8a6100}.not-useful{color:#b3261e}
ul{margin:8px 0 0;padding-left:20px}li{margin:6px 0}
.ev{display:block;color:var(--muted);font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;overflow-wrap:anywhere}
.turn{margin:14px 0;padding-left:14px;border-left:3px solid var(--line)}.note{color:var(--muted);font-size:13px;font-style:italic}
footer{margin-top:40px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}
@media print{main{padding:0}h2{break-after:avoid}}
`;

export function reportHtml(room: RoomState, names: Names): string {
  if (!room.project) return "";
  const name = (id: string) => esc(names[id] ?? id);
  const tag = (s: Stance) => `<span class="tag ${s.replace(" ", "-")}">${s}</span>`;
  const list = (items: string[]) => `<ul>${items.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`;
  const claims = (cs: Claim[], lost = 0) =>
    cs.length || lost
      ? `<ul>${cs.map((c) => `<li>${esc(c.text)}<span class="ev">${esc(evidence(c))}</span></li>`).join("")}` +
        `${lost ? `<li class="note">${dropped(lost)}</li>` : ""}</ul>`
      : "";
  const p = room.project;
  const parts: string[] = [
    `<h1>Is ${esc(p.name)} useful?</h1>`,
    `<div class="meta">${esc(p.repo_url)}<br>${esc(sources(room))}</div>`,
  ];
  if (room.summary) {
    const s = room.summary;
    parts.push(`<section class="sum"><div>${STANCES.filter((x) => s.tally[x]).map((x) => `${tag(x)} ×${s.tally[x]}`).join(" ")}</div>` +
      `<div class="head">${esc(s.headline)}</div>` +
      ([["Agreed", s.agreed], ["Split", s.split], ["Top changes", s.top_changes]] as const)
        .map(([label, items]) => (items.length ? `<h3>${label}</h3>${list(items)}` : "")).join("") + `</section>`);
  }
  if (room.verdicts.length)
    parts.push(`<h2>Final verdicts</h2>` + room.verdicts.map((v) =>
      `<div class="card"><h3>The ${name(v.persona_id)} ${tag(v.verdict)}</h3><div>${esc(v.headline)}</div>` +
      claims(v.reasons, v.rejected.length) +
      (v.what_would_change_my_mind.length ? `<p><strong>What would change my mind</strong></p>${list(v.what_would_change_my_mind)}` : "") +
      `</div>`).join(""));
  if (room.impressions.length)
    parts.push(`<h2>Round 1 · First impressions</h2>` + room.impressions.map((i) =>
      `<div class="card"><h3>The ${name(i.persona_id)} ${tag(i.stance)}</h3><div>${esc(i.headline)}</div>${claims(i.claims, i.rejected.length)}</div>`).join(""));
  if (room.answered.length)
    parts.push(`<h2>Questions to the builder</h2>` + room.answered.map((a) =>
      `<p><strong>${esc(a.question.text)}</strong><br>${a.answer ? esc(a.answer) : "<em>Skipped</em>"}</p>`).join(""));
  const turns = room.feed.flatMap((f) => (f.kind === "turn" && !f.turn.error ? [f.turn] : []));
  if (turns.length)
    parts.push(`<h2>Round 2 · Debate</h2>` + turns.map((t) =>
      `<div class="turn"><strong>${name(t.speaker)}</strong> ${tag(t.stance)}` +
      (t.contrarian ? ` <span class="note">arguing the other side</span>` : "") +
      `<div>${esc(t.message)}</div>` +
      (t.stance_changed ? `<div class="note">Changed stance to ${t.stance}: ${esc(t.stance_change_reason ?? "")}</div>` : "") +
      claims(t.claims, t.rejected.length) + `</div>`).join(""));
  parts.push(`<footer>Reviewed by Project Jury. Every claim was checked by code against the repository, demo or live site; claims whose quote could not be found were dropped.</footer>`);
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">` +
    `<title>${esc(p.name)} · Project Jury review</title><style>${CSS}</style></head><body><main>${parts.join("\n")}</main></body></html>`;
}

export function download(name: string, text: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
