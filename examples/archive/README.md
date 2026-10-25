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
