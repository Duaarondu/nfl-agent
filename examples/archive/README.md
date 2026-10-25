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
