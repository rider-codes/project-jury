Give your first impression of this project. Your question is: "{verdict_question}"

You have not heard from the other reviewers yet. Judge on your own, against your rubric.

Reply with ONLY a JSON object of this shape:

{{
  "stance": "useful" | "unsure" | "not useful",
  "headline": "one short line",
  "claims": [
    {{"text": "your point", "evidence": {{"kind": "file" | "demo", "ref": "path/or/step-ref", "quote": "exact text copied from it"}}}}
  ],
  "questions": ["question for the builder, only if something you need is missing"]
}}

Give 1 to 3 claims. Ask at most 2 questions, and only ones whose answer could change your stance. Use "unsure" when key evidence is missing.
