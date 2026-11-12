Give your final verdict on this project. Answer your question: "{verdict_question}"

Reply with ONLY a JSON object of this shape:

{{
  "verdict": "useful" | "unsure" | "not useful",
  "headline": "one short line",
  "reasons": [
    {{"text": "your point", "evidence": {{"kind": "file" | "demo" | "tree", "ref": "path, step-ref, or present/absent", "quote": "exact text copied from it"}}}}
  ],
  "what_would_change_my_mind": ["concrete change"],
  "questions": ["question for the builder, only if something you need is missing"]
}}

Give 2 to 5 reasons. "useful" maps to yes, "not useful" to no, "unsure" when evidence is missing.
