Below are $n short video clips from a drama, written as screenplay text with timestamps relative to the start of each clip. CAMERA lines describe what is on screen. For each clip, "FIRST 3 SECONDS" is everything the viewer gets before deciding to keep watching.

$clips

For EACH clip, answer as the stranger described:
- cold_viewer: who are these people (as far as you can tell), what is happening, what do you want to know next; understood = can you follow the situation without any outside context; clarity 1-10.
- three_sec: from the FIRST 3 SECONDS only, would you stop scrolling? score 1-10 and why (one short line).
- cliffhanger: does the clip end on an unresolved moment that makes you need the next part? score 1-10.
- outcomes: list 4-5 distinct things that could plausibly happen right after the clip ends, each with your probability p (they must sum to about 1).
- ad_risk: would TikTok or Meta ad review likely restrict this clip as a paid ad (graphic violence, physical abuse, sexual content, self-harm, weapons)? level low/medium/high and a short reason.

Return JSON:
{"clips": [{"id": "...", "cold_viewer": {"who": "...", "what": "...", "want_next": "...", "understood": true, "clarity": 7},
  "three_sec": {"stop": true, "score": 8, "why": "..."}, "cliffhanger": {"unresolved": true, "score": 8},
  "outcomes": [{"outcome": "...", "p": 0.4}], "ad_risk": {"level": "low", "reason": "..."}}]}
