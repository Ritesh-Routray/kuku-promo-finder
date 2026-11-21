SHOW: $show
EPISODE: $ep of $total (length $duration)

PREVIOUSLY (for your understanding only; a promo viewer has NOT seen this):
$previously

RELATED EARLIER SCENES (retrieved by similarity):
$related

DRAMA HEARTBEAT: the highest-intensity moments in this episode, measured from emotion, events and camera cutting, are at: $peaks

SCRIPT (every line has [start-end] timestamps in mm:ss.cc; CAMERA lines describe what is on screen):
$script

TASK
Propose $k different promo clips taken from THIS episode. A promo is a 20-60 second clip posted on TikTok/Reels/Shorts to pull in new viewers. Each promo must:
1. OPEN ON A HOOK: the first segment must start on (or within 3 seconds before) a scroll-stopping moment: a slap, a reveal, a shocking or cruel line, a public humiliation.
2. END ON A CLIFFHANGER: the last segment ends right after a line or action that leaves a question open. Cut BEFORE the answer arrives.
3. MAKE SENSE ON ITS OWN to someone who has never seen the show.
4. Total length 20-60 seconds. Use 1 segment if possible; at most 3 segments, in story order, all from this episode.
5. Use timestamps copied exactly from the script line boundaries. Prefer moments near the heartbeat peaks, but use your judgement.
6. Make the $k promos different from each other (different hooks or different questions).

Return JSON:
{"promos": [{
  "title": "3-6 word working title",
  "segments": [{"start": "mm:ss.cc", "end": "mm:ss.cc"}],
  "hook_line": "the exact script text of the hook moment (dialogue or action)",
  "cliffhanger_line": "the exact script text of the final unresolved moment",
  "open_question": "the question the viewer is left with",
  "archetype": "one of: betrayal, humiliation, slap/violence, hidden identity, revenge, forbidden romance, family villainy, threat/danger, power reversal, secret revealed, other",
  "why": "one line on why this works as a promo"
}]}
