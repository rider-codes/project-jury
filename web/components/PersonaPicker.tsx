import { STANCE_COLOR, STANCE_LABEL, portrait } from "@/lib/personas";
import type { PersonaState } from "@/lib/room";
import type { Persona, Stance } from "@/lib/types";
import { Icon, accentStyle } from "./bits";

type Props = {
  personas: Persona[];
  selected: string[];
  onToggle?: (id: string) => void; // undefined once the review has started
  stance?: Record<string, Stance>;
  state?: Record<string, PersonaState>;
  speaking?: string | null;
  single?: boolean; // one-on-one: pick exactly one
};

function statusLine(id: string, inRoom: boolean, started: boolean, stance?: Stance, st?: PersonaState) {
  if (!started) return inRoom ? { text: "In the room", color: "#A6B0CC" } : { text: "Add to room", color: "#A6B0CC" };
  if (!inRoom) return { text: "Not in this review", color: "#8F9AB8" };
  if (st === "waiting") return { text: "Waiting for you", color: "#A5B4FC" };
  if (st === "error") return { text: "Could not answer", color: "#FCA5A5" };
  if (st === "thinking") return { text: "Thinking", color: "#A6B0CC", thinking: true };
  if (stance) return { text: STANCE_LABEL[stance], color: STANCE_COLOR[stance] };
  return { text: "", color: "#A6B0CC" };
}

export function PersonaPicker({ personas, selected, onToggle, stance = {}, state = {}, speaking, single }: Props) {
  const started = !onToggle;
  return (
    <div className="personas" role={single ? "radiogroup" : undefined}>
      {personas.map((p) => {
        const on = selected.includes(p.id);
        const line = statusLine(p.id, on, started && !single, stance[p.id], state[p.id]);
        return (
          <button
            key={p.id}
            type="button"
            className={`persona ${on ? "" : "off"} ${speaking === p.id ? "speaking" : ""}`}
            style={accentStyle(p.id)}
            aria-pressed={single ? undefined : on}
            role={single ? "radio" : undefined}
            aria-checked={single ? on : undefined}
            aria-disabled={started && !single}
            onClick={() => onToggle?.(p.id)}
            title={p.verdict_question}
          >
            <div className="portrait">
              <img src={portrait(p.id)} width={138} height={155} alt="" />
              {on && <span className="check">{Icon.check}</span>}
            </div>
            <span className="persona-name">{p.name}</span>
            <span className="persona-tag">{p.tagline}</span>
            <span className={`persona-state ${line.thinking ? "thinking" : ""}`} style={{ color: line.color }}>
              {single ? (on ? "Chatting" : "Pick") : line.text}
            </span>
          </button>
        );
      })}
    </div>
  );
}
