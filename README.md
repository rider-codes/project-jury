# Project Jury

A panel of AI reviewers that reads your software project and tells you, with evidence, whether it is useful.

It is for solo builders and students with a side project or portfolio piece and nobody to give them honest
feedback. You give a public GitHub link, a live site, or both (and optionally a short walkthrough). Up to six
reviewers read it, ask you what is missing, debate each other, and each give a verdict: useful, unsure or
not useful.

What makes it different from asking a chatbot: **no evidence, no claim**. Every point a reviewer makes must
quote a file, a demo step, the live site or one of your answers. A checker written in plain code
(`jury/verifier.py`, no model) looks each quote up and drops anything it cannot find.

Live demo: <https://project-jury.onrender.com>. Anyone can watch a real review replayed there and run their
own. Reviews use the host's free model quota; when it runs out for the day, the page asks for your own
OpenRouter key (see "Bring your own key").

## The reviewers

| Reviewer | Their question |
|---|---|
| Senior engineer | Would I trust this code? |
| Product manager | Would anyone use this? |
| UX designer | Is the first run clear? |
| General user | Would I use this? |
| Hiring manager | Would I hire this builder? |
| Open-source maintainer | Would I contribute to this? |

The first four are the default room. Each reviewer is a prompt file in `personas/`.

## Quickstart

You need Python 3.11+, [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
uv sync
cd web && npm install && cd ..
```

**Try it with no API key.** The demo model is free and offline; its opinions are canned, so use it to see
the flow, not to judge a project.

```bash
uv run python -m jury.api --demo-model --db jury_demo.sqlite
cd web && npm run dev
```

Open <http://localhost:3000>, paste any public GitHub link and press **Start review**.

**Run real reviews.** Copy `.env.example` to `.env`, set `JURY_PROVIDER` and its key (`OPENROUTER_API_KEY`
or `GEMINI_API_KEY`), and set a model id for `JURY_MODEL_CHEAP`, `JURY_MODEL_MID` and `JURY_MODEL_STRONG`.
Free OpenRouter models end in `:free`. A `GITHUB_TOKEN` is optional but raises GitHub's limit from 60 to
5,000 requests an hour.

```bash
uv run python -m jury.api
cd web && npm run dev
```

To let reviewers look at a live site, install the headless browser once:
`uv run python -m playwright install chromium`.

## How a review runs

1. **Read.** The repo is fetched as one tarball and cut down to a size-capped brief. A live site, if given,
   is captured on desktop and phone and described once.
2. **First impressions.** Every reviewer answers in parallel. Their questions to you are merged and shown
   as cards; the review pauses until you answer or skip.
3. **Debate.** A router written in code (no model) picks the next speaker: whoever is most challenged.
   You can message the room while it runs.
4. **Verdicts.** Each reviewer gives a structured verdict with reasons and what would change their mind,
   then a short summary is written.

After a review you can talk to one reviewer on their own, with or without the room's history. Pick only one
reviewer before starting and it is a one-on-one from the start: they give their verdict, then you can ask them
about it.

## Limits

- Public GitHub repos only.
- A default review of four reviewers makes about 17 model requests. A repo at the brief's size cap costs
  roughly 770k input tokens; `JURY_MAX_TOKENS` caps one review (1.2M by default).
- OpenRouter's free tier allows 50 requests a day, so about two reviews.
- Free hosts have no persistent disk, so past reviews reset on every restart.

## Bring your own key

When the shared free quota hits 0, the page asks the visitor for their own OpenRouter key (they can also
open the card any time with "Use your own key"). Their runs then spend their account, not yours.

- The key stays in the browser tab (`sessionStorage`) and is sent in an `X-Jury-Key` header. The server holds
  it in memory only while a run uses it, never writes it to the database or logs, and hides it from error
  text (`jury/redact.py`).
- With a key, the models come from `JURY_BYOK_MODEL_CHEAP` / `_MID` / `_STRONG` / `_VISION` when set (use
  paid models there), else the usual `JURY_MODEL_*`. A free-model key still hits its own daily cap.
- `python -m jury.api --demo-byok` pretends the shared quota is gone and accepts any key, for working on the
  screens offline.

## Tests

```bash
uv run pytest
cd web && npx tsc --noEmit
uv run python -m jury.eval
```

The last one runs the eval set in `evals/cases.yaml` against real models (about 27 requests) and exits 1
if a case fails. Add `--demo-model` to check only the plumbing.

## Deploying

`Dockerfile` builds the web app to static files and serves them from the API. `render.yaml` is a Render
blueprint for the free plan. The deployment is open: no access code. Leave `JURY_ACCESS_CODE` unset for that;
set it only to lock a private instance (`NEXT_PUBLIC_REQUEST_CODE_URL`, at build time, sets where the "Request
one here" link goes). Open means anyone can use the free quota, and every visitor can currently see every
past review and chat, since history is not separated per visitor yet.

## Layout

| Path | What is in it |
|---|---|
| `jury/ingest/` | GitHub download, file selection, live-site capture, the brief |
| `jury/room/` | The LangGraph room: first impressions, question dedupe, router, debate, verdicts |
| `jury/verifier.py` | The claim checker |
| `jury/llm.py` | Provider swap, model tiers, retries, the per-review budget |
| `jury/api/` | FastAPI app, event stream, access code |
| `personas/`, `prompts/` | Reviewer definitions and prompt text |
| `web/` | The Next.js front end |
| `evals/` | The eval cases |
