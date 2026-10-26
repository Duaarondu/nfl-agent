# Archived example runs

Older runs kept for reference; the current examples are one level up in `examples/`.
Each `answer.md` says at the top where its data came from and which steps were model
vs rule-based (runs from before that header was added do not).

- `who-becomes-the-bucs-wr1-if-mike-evans-is-out/20261022-234321-d52e2e813360` is the
  saved Analyst answer ("Start Deebo Samuel") that `scripts/demo_critic.py` feeds into
  the live Critic loop; its output is `examples/critic-demo-*/`.
- `why-is-christian-watson-.../20261025-154203-7da78fe4625c` and `.../20261025-155219-1f70a86c1057`
  are the Nightshift preset comparison runs (default vs "Highest quality"); in the second,
  slow live queries left the factor agents a 16s window, which led to the guaranteed
  60s minimum (analyst.MIN_FACTOR_WINDOW).
- `should-i-pick-up-a-49ers-receiver-if-evans-misses-time/20261025-163512-994c234341e5`
  answered "Pick up Mike Evans" (the player who is out) and was approved; it led to the
  replacement routing for "if <player> misses time" and critic check (d)'s out-player rule.
  It and the Bucs and league-memory runs from the same batch (ddb115ab07ae, 03f78201f109)
  predate the "<depth chart pick> is next ..., so for fantasy: ..." answer shape.
- `start-mcbride-or-brock-bowers/20261025-193926-9fff19ee315b` is the second run of the
  McBride/Bowers rerun (full name for Bowers). It reached the same verdict in 79.2s, but
  two factor summaries had numbers the Critic could not find in the rows (3.4, 0.4), so
  the run of the question as written is the one kept.

### Replaced on 25 October 2026 by the rerun-4 examples (`20261025-22*`)

Rerun 4 is the first set run on the final code (matchup labels, bye rule, suffix-aware
names, review-timeout skip). Every run below was replaced for the reason given.

| Run | Batch | Reason |
|---|---|---|
| `why-is-christian-watson-.../20261025-162014-c86443db3074` | previous README example | 349.9s; first verdict and both critic reviews fell back to rules. |
| `who-becomes-the-bucs-.../20261025-171146-c8005cf773a5` | previous README example | Same verdict (Kittle), but the critic review fell back to rules; 148.4s. |
| `12-team-half-ppr-.../20261025-171545-737f52e76684` | previous README example | Rule-based verdict and rule-based critic review (model calls failed); 238.5s. |
| `should-i-pick-up-a-49ers-.../20261025-171850-c6bfcb00aeb7` | previous README example | Rule-based verdict and critic review; 184.9s. |
| `who-should-i-start-trey-mcbride-.../20261025-193807-e7adc890c23c` | previous README example | Same verdict (Bowers), 153.6s; predates the matchup labels. |
| `i-have-jameson-williams-.../20261025-180054-2d2fcbc02978` | previous README example | Same verdict (Pickens), 128.7s; predates the matchup labels. |
| `critic-demo-.../20261025-125256-5cfacb69069d` | previous README example | Critic reviews and revised verdict fell back to rules; 170.8s. |
| `*/20261025-1947*` to `*/20261025-1957*` (7 runs) | rerun 1 | First rerun after the critic fixes; e.g. league c1 answered "start George Kittle over Davante Adams" (off-question) before round 2 fixed it. Code changed after. |
| `*/20261025-2041*` to `*/20261025-2049*` (7 runs) | rerun 2 | Before the polarity-aware direction check and hard-rule fallback; e.g. league c1's first draft picked up Deebo Samuel (11.1%) over McCaffrey (22.8%). |
| `why-is-christian-watson-.../20261025-210527-a412694d9720` | rerun 3 | Approved, but predates the matchup labels and number-in-rows check. |
| `who-becomes-the-bucs-.../20261025-210626-1da9ef0b113f` | rerun 3 | Approved (Kittle); predates the final code. |
| `12-team-half-ppr-.../20261025-210849-cb521191f693` | rerun 3 | Approved (McCaffrey); predates the final code. |
| `should-i-pick-up-a-49ers-.../20261025-211011-7afb9aeb5276` | rerun 3 | Approved (McCaffrey); predates the final code. |
| `i-have-jameson-williams-.../20261025-211041-d4aafb841110` | rerun 3 | Approved (Pickens); predates the final code. |
| `who-should-i-start-trey-mcbride-.../20261025-211220-aa7c55b91bec` | rerun 3 | Approved with a wrong claim: a "target volume edge" for Bowers (McBride had 65 targets to 43). |
| `critic-demo-.../20261025-211259-82453ba2c4ac` | rerun 3 | Approved with a wrong depth-chart claim about Kittle. |

### Replaced on 26 October 2026 after the stand-in fix (`20261026-15*`)

QA found that a replacement pick came from the whole team's target share, so a TE or an RB
could replace a WR. A stand-in is now a player at the out player's position, ranked below him
on the depth chart, who can play. These four runs recommended the wrong position and were
rerun with fresh IDs.

| Run | Answer | Reason |
|---|---|---|
| `who-becomes-the-bucs-.../20261025-222542-1b1452e42db5` | Pick up George Kittle (TE) | Kittle is a TE, not a WR below Evans. New: Deebo Samuel (`56933e43f91f`). |
| `12-team-half-ppr-.../20261025-222610-ad669548f7c3` | Pick up Christian McCaffrey (RB) | McCaffrey is an RB. New: Deebo Samuel (`17279d592b6c`). |
| `should-i-pick-up-a-49ers-.../20261025-222628-afedf66887d9` | Pick up McCaffrey (RB) | Same. New: Deebo Samuel (`9bb4fcf8f300`). |
| `should-i-start-bucky-irving-.../20261026-154259-729276b497e3` | Start Taylor, approved | Approved saying Taylor "faces a more favorable matchup ... (CAR rank 5 vs MIN rank 32)"; MIN (Taylor's) is rank 32, tough. The direction check gave the claim to Irving because CAR came first; fixed and rerun. |
| `should-i-start-bucky-irving-.../20261026-154806-3b58e676ab5c` | Start Taylor, approved | Round 1 caught the reversal, but round 2 was approved with "He also faces the easier matchup: Bucky Irving plays CAR"; "He" (Taylor, from the sentence before) was read as Irving. Fixed and rerun (`7fef4f2eb859`). |
| `critic-demo-.../20261025-222901-19b0e0886ff8` | Revised "Start Deebo Samuel" to "pick up George Kittle" | The Critic pushed the answer to a TE. New: the revision keeps Samuel (`27d4fa9cc227`). |
