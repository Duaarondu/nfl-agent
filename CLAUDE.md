# NFL Agent – Open Agent Hackathon 2026

## What this is
Multi-agent assistant answering NFL questions from nflverse data.
Agents: Planner, Analyst, Critic. Python 3.10+.
Track and target user: not decided yet.

## Architecture rules
- Agents live in app/agents/. Each has its own system prompt and tools.
- ALL model calls go through app/adapters/meterless.py (OpenAI-compatible,
  Meterless Nightshift Runtime). Never call NVIDIA or any provider directly.
- ALL data queries go through app/adapters/zetaris.py (run_sql). One SQL
  statement per call. For now, use the Zetaris UI-proxy route
  (POST {ZETARIS_BASE_URL}/api/proxy/sql-editor/sqls/run-query).
- Every adapter call has a timeout and a fallback.
- SAMPLE_MODE=true: adapters read cached data from data/sample/. Agents still
  run real logic. Never load prewritten final answers.
- Every agent step writes a JSONL trace line to stdout and logs/
  (timestamp, agent_name, action, target_agent, status, retry_count).
- Max 3 critic rounds per question.
- Entry point: POST /run (JSON in, JSON out) in run.py.
- At least one Meterless Engine (H-MEM, Markovian, World Model or Scout
  Intent) must power a real feature, with a passing test.

## Data
- nflverse via nflreadpy. Never commit full datasets; only small slices in
  data/sample/.
- Credit nflverse (CC-BY 4.0) and FTN charting data (CC-BY-SA 4.0,
  "FTN Data via nflverse") in the README.

## Secrets
- Settings come from .env (gitignored). .env.example has placeholders only.
- Never print, log or hardcode keys. Never ask me to paste keys into chat.

## Commands
- Run tests: pytest
- Run app: python run.py
