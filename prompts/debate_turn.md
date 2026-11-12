It is your turn in the debate. Read the room transcript above.

Your current stance is "{stance}". Your question is still: "{verdict_question}"

The other reviewers in the room (use these ids in "challenges"):
{others}
{user_message}
Do one of these, in character:
- Answer the strongest challenge against you, with evidence.
- Challenge another reviewer whose point the evidence does not support.
- Raise a point nobody has made yet.

Do not repeat points already made. Only change your stance if the evidence or an answer from the builder gives you a reason; if you change it, say why in "stance_change_reason".

Reply with ONLY a JSON object of this shape:

{{
  "message": "3 to 5 sentences, said to the room",
  "claims": [
    {{"text": "point", "evidence": {{"kind": "file" | "demo" | "tree", "ref": "path, step-ref, or present/absent", "quote": "exact text copied from it"}}}}
  ],
  "stance": "useful" | "unsure" | "not useful",
  "stance_change_reason": null,
  "new_point": true,
  "challenges": ["persona_id you dispute"],
  "open_question": null
}}

Give 0 to 2 claims. Set "new_point" to false if you are only agreeing or restating. Use "open_question" only for one fact only the builder can answer.
