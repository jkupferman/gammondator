# Gammondator

Gammondator is a backgammon decision-coach backend. It analyzes your played move against candidate moves and returns:

- best move by equity
- your move quality (`excellent`, `good`, `inaccuracy`, `mistake`, `blunder`)
- plain-language reasons based on structural/racing heuristics

This is an MVP foundation designed to plug into a stronger engine (e.g. GNU Backgammon) later.

## Web Trainer Highlights

- Rendered backgammon board with CSS points, bar, and off trays.
- Click/tap/drag move input with legal source/target enforcement.
- Legal destination highlighting for selected checkers.
- Session gameplay loop controls (new, roll, AI turn, close, report).
- Session gameplay loop controls (new, roll, AI suggest, AI turn, close, report).
- Session resume picker for existing profile sessions.
- Session move log restored from backend turn history on resume.
- Move log with quality/equity-loss tags.
- Move feedback summary in readable coaching format.
- Auto AI reply toggle for faster training cycles.
- Training dashboard, cube trainer, drill workflow, and analysis queue controls.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

Server runs at `http://127.0.0.1:8000`.

## Endpoints

- `GET /health`
- `GET /analyzer`
- `POST /analysis-jobs`
- `GET /analysis-jobs`
- `GET /analysis-jobs/stats`
- `GET /analysis-jobs/{job_id}`
- `POST /analysis-jobs/{job_id}/run`
- `POST /analysis-jobs/{job_id}/retry`
- `DELETE /analysis-jobs/{job_id}`
- `POST /analysis-jobs/run-next`
- `POST /analysis-jobs/run-batch`
- `POST /analysis-jobs/cleanup`
- `POST /sessions`
- `GET /sessions/{session_id}`
- `GET /sessions/{session_id}/turns`
- `GET /sessions/{session_id}/turns/markdown`
- `POST /sessions/{session_id}/play-turn`
- `POST /sessions/{session_id}/ai-turn`
- `POST /sessions/{session_id}/roll`
- `POST /sessions/{session_id}/close`
- `GET /sessions/{session_id}/report`
- `POST /analyze-move`
- `POST /choose-ai-move`
- `POST /legal-moves`
- `POST /analyze-position`
- `POST /choose-ai-move-from-position`
- `POST /rate-played-move`
- `POST /rate-played-move-and-record`
- `GET /training/summary`
- `GET /training/mistakes`
- `GET /training/leaks`
- `GET /training/drills`
- `POST /training/drills/attempt`
- `GET /training/drills/summary`
- `GET /training/dashboard`
- `GET /training/report`
- `GET /training/report/markdown`
- `POST /cube/decision`

## Example Request

```bash
curl -X POST 'http://127.0.0.1:8000/analyze-move' \
  -H 'Content-Type: application/json' \
  -d '{
    "position": {
      "points": [-2,0,0,0,0,5,0,3,0,0,0,-5,5,0,0,0,-3,0,-5,0,0,0,0,2],
      "bar_white": 0,
      "bar_black": 0,
      "off_white": 0,
      "off_black": 0,
      "turn": "white",
      "cube_value": 1,
      "dice": [6,1]
    },
    "played_move": {
      "notation": "24/18 8/7",
      "steps": [
        {"from_point": 24, "to_point": 18},
        {"from_point": 8, "to_point": 7}
      ]
    },
    "candidate_moves": [
      {
        "notation": "13/7 8/7",
        "steps": [
          {"from_point": 13, "to_point": 7},
          {"from_point": 8, "to_point": 7}
        ]
      },
      {
        "notation": "24/18 8/7",
        "steps": [
          {"from_point": 24, "to_point": 18},
          {"from_point": 8, "to_point": 7}
        ]
      },
      {
        "notation": "24/23 13/7",
        "steps": [
          {"from_point": 24, "to_point": 23},
          {"from_point": 13, "to_point": 7}
        ]
      }
    ]
  }'
```

## Server-Side Legal Move Generation

Request all legal plays for the current turn:

```bash
curl -X POST 'http://127.0.0.1:8000/legal-moves' \
  -H 'Content-Type: application/json' \
  -d '{ "position": { ...same position payload... } }'
```

## Session Gameplay Loop

Create a session with an initial position:

```bash
curl -X POST 'http://127.0.0.1:8000/sessions' \
  -H 'Content-Type: application/json' \
  -d '{ "initial_position": { ...position payload... }, "profile_id": "default" }'
```

Play a turn in that session (rate move, advance board, set next dice):

```bash
curl -X POST 'http://127.0.0.1:8000/sessions/1/play-turn' \
  -H 'Content-Type: application/json' \
  -d '{ "played_move": { ... }, "next_dice": [3,2], "record_training": true }'
```

Roll fresh dice for the current session position:

```bash
curl -X POST 'http://127.0.0.1:8000/sessions/1/roll'
```

Close a session:

```bash
curl -X POST 'http://127.0.0.1:8000/sessions/1/close'
```

Have AI choose and apply a turn in that session:

```bash
curl -X POST 'http://127.0.0.1:8000/sessions/1/ai-turn' \
  -H 'Content-Type: application/json' \
  -d '{ "next_dice": [4,2], "apply_move": true }'
```

Get a post-game style session report:

```bash
curl 'http://127.0.0.1:8000/sessions/1/report?top_n=5'
```

Load ordered turn history for a session:

```bash
curl 'http://127.0.0.1:8000/sessions/1/turns?limit=200'
curl 'http://127.0.0.1:8000/sessions/1/turns?limit=200&actor=human'
curl 'http://127.0.0.1:8000/sessions/1/turns/markdown?limit=200&actor=ai'
```

Choose an AI move directly from `position + dice` (no client candidate list needed):

```bash
curl -X POST 'http://127.0.0.1:8000/choose-ai-move-from-position' \
  -H 'Content-Type: application/json' \
  -d '{ "position": { ...same position payload... } }'
```

Analyze a full turn from `position + dice` and get ranked top moves:

```bash
curl -X POST 'http://127.0.0.1:8000/analyze-position' \
  -H 'Content-Type: application/json' \
  -d '{ "position": { ...same position payload... } }'
```

Rate a human move directly from `position + played_move` (server generates legal candidates):

```bash
curl -X POST 'http://127.0.0.1:8000/rate-played-move' \
  -H 'Content-Type: application/json' \
  -d '{ "position": { ... }, "played_move": { ... } }'
```

Persist a rated move to training history:

```bash
curl -X POST 'http://127.0.0.1:8000/rate-played-move-and-record' \
  -H 'Content-Type: application/json' \
  -d '{ "position": { ... }, "played_move": { ... } }'
```

Read training stats:

```bash
curl 'http://127.0.0.1:8000/training/summary?profile_id=default'
curl 'http://127.0.0.1:8000/training/mistakes?limit=20&profile_id=default'
curl 'http://127.0.0.1:8000/training/leaks?profile_id=default'
curl 'http://127.0.0.1:8000/training/drills?limit=10&profile_id=default'
curl 'http://127.0.0.1:8000/training/drills/summary?profile_id=default'
curl 'http://127.0.0.1:8000/training/dashboard?profile_id=default'
curl 'http://127.0.0.1:8000/training/report?profile_id=default'
curl 'http://127.0.0.1:8000/training/report/markdown?profile_id=default'
```

Submit a drill answer:

```bash
curl -X POST 'http://127.0.0.1:8000/training/drills/attempt' \
  -H 'Content-Type: application/json' \
  -d '{ "review_id": 1, "chosen_notation": "13/7 8/7", "profile_id": "default" }'
```

Cube decision training:

```bash
curl -X POST 'http://127.0.0.1:8000/cube/decision' \
  -H 'Content-Type: application/json' \
  -d '{ "position": { ... }, "action": "nodouble" }'
```

## Deferred Analysis Jobs

Queue an analysis job:

```bash
curl -X POST 'http://127.0.0.1:8000/analysis-jobs' \
  -H 'Content-Type: application/json' \
  -d '{ "profile_id": "default", "analysis_mode": "deep", "position": { ... } }'
```

Run queued jobs:

```bash
curl -X POST 'http://127.0.0.1:8000/analysis-jobs/1/run'
curl -X POST 'http://127.0.0.1:8000/analysis-jobs/1/retry'
curl -X DELETE 'http://127.0.0.1:8000/analysis-jobs/1'
curl -X POST 'http://127.0.0.1:8000/analysis-jobs/run-next?profile_id=default'
curl -X POST 'http://127.0.0.1:8000/analysis-jobs/run-batch?profile_id=default&limit=20'
curl -X POST 'http://127.0.0.1:8000/analysis-jobs/cleanup?profile_id=default'
```

Inspect jobs:

```bash
curl 'http://127.0.0.1:8000/analysis-jobs?profile_id=default'
curl 'http://127.0.0.1:8000/analysis-jobs/stats?profile_id=default'
curl 'http://127.0.0.1:8000/analysis-jobs/1'
```

Background worker (local process):

```bash
GAMMONDATOR_WORKER_PROFILE_ID=default \
GAMMONDATOR_WORKER_BATCH_SIZE=20 \
.venv/bin/python scripts/analysis_job_worker.py
```

## Web Board MVP

Run the API and open the root URL:

- [http://127.0.0.1:8000](http://127.0.0.1:8000)

The web UI supports:
- session creation
- profile selection (`profile_id`)
- backgammon-style rendered board (points, bar, stacked checkers)
- legal move loading
- click-based move builder + submit
- AI turn button
- roll button and session close action
- session report and training summary panels
- cube trainer decision checker panel
- drill mode load/answer flow
- analysis queue create/run-next controls and job list
- retry-latest-job control
- cleanup-finished-jobs control

## Testing

```bash
python -m pytest -q
```

## Engine Backends

By default, Gammondator uses the built-in heuristic analyzer.

To enable GNU Backgammon analysis through an external bridge process:

```bash
export GAMMONDATOR_ANALYZER=gnubg
export GAMMONDATOR_GNUBG_BRIDGE_CMD='path/to/gnubg_bridge'
```

Local wiring test command:

```bash
export GAMMONDATOR_ANALYZER=gnubg
export GAMMONDATOR_GNUBG_BRIDGE_CMD='.venv/bin/python scripts/gnubg_bridge_stub.py'
```

Real GNUbg bridge command:

```bash
export GAMMONDATOR_ANALYZER=gnubg
export GAMMONDATOR_GNUBG_BRIDGE_CMD='.venv/bin/python scripts/gnubg_bridge_real.py'
export GNUBG_BIN='/opt/local/bin/gnubg'
```

Optional:

```bash
export GAMMONDATOR_FALLBACK_TO_HEURISTIC=0
export GAMMONDATOR_GNUBG_EVAL_MODE=2ply     # 0ply, 1ply, or 2ply
export GAMMONDATOR_GNUBG_TIMEOUT=15
export GAMMONDATOR_GNUBG_CACHE=1
export GAMMONDATOR_GNUBG_CACHE_DB='gammondator_gnubg_cache.db'
export GAMMONDATOR_CUBE_ENGINE=1            # use GNUbg proper cube action in /cube/decision
export GAMMONDATOR_GNUBG_DEEP_TIMEOUT=45
export GAMMONDATOR_GNUBG_DEEP_EVAL_MODE=2ply
```

Bridge contract:

- Input: `AnalyzeMoveRequest` JSON via stdin
- Output: JSON via stdout with required `equities` and optional `reasons`

```json
{
  "equities": {
    "13/7 8/7": 0.1123,
    "24/18 13/7": 0.0940
  },
  "reasons": {
    "13/7 8/7": ["Improves board structure.", "Reduces direct shots."]
  }
}
```

`equities` keys must match candidate move notations.

## Training Store

Recorded training data is stored in a local SQLite database.

- Default path: `gammondator.db`
- Override with env var:

```bash
export GAMMONDATOR_DB_PATH='/absolute/path/to/gammondator.db'
```

## Notes

- Endpoints that accept user-provided moves now enforce strict legality for the supplied `position + dice`.
- Session turn endpoints auto-roll next dice when `next_dice` is omitted.
- Training and session history are profile-scoped via `profile_id` (default is `default`).
- GNUbg backend can automatically fall back to heuristic backend per request when enabled.
