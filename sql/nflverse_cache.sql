-- Rerun after the Zetaris cluster restarts. One statement per run_sql call.
-- All seven tables the agents query: uncached ones (e.g. injuries) can take 60s+.
CACHE TABLE NFLVERSE.pbp;

CACHE TABLE NFLVERSE.player_stats;

CACHE TABLE NFLVERSE.snap_counts;

CACHE TABLE NFLVERSE.depth_charts;

CACHE TABLE NFLVERSE.injuries;

CACHE TABLE NFLVERSE.rosters;

CACHE TABLE NFLVERSE.schedules;
