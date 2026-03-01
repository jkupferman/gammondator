#!/usr/bin/env python3
"""
Simple analysis-job worker for Gammondator.

Runs pending analysis jobs from SQLite queue without requiring manual API calls.

Env vars:
- GAMMONDATOR_WORKER_PROFILE_ID: optional profile filter
- GAMMONDATOR_WORKER_BATCH_SIZE: jobs per tick (default 10)
- GAMMONDATOR_WORKER_POLL_SECONDS: sleep when queue empty (default 2)
- GAMMONDATOR_WORKER_MAX_TICKS: stop after N ticks (default 0 -> infinite)
"""

from __future__ import annotations

import os
import time

from app.main import _run_analysis_job, analysis_store


def main() -> int:
    profile_id = os.getenv("GAMMONDATOR_WORKER_PROFILE_ID") or None
    batch_size = max(1, int(os.getenv("GAMMONDATOR_WORKER_BATCH_SIZE", "10")))
    poll_seconds = max(0.1, float(os.getenv("GAMMONDATOR_WORKER_POLL_SECONDS", "2")))
    max_ticks = max(0, int(os.getenv("GAMMONDATOR_WORKER_MAX_TICKS", "0")))

    tick = 0
    while True:
        tick += 1
        processed = 0

        for _ in range(batch_size):
            next_job = analysis_store.next_pending_job(profile_id=profile_id)
            if next_job is None:
                break

            job_id = int(next_job["job_id"])
            result = _run_analysis_job(job_id)
            print(f"job={job_id} status={result.status}")
            processed += 1

        if processed == 0:
            print("idle")
            time.sleep(poll_seconds)

        if max_ticks and tick >= max_ticks:
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
