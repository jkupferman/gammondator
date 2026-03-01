# Gammondator

Gammondator is a backgammon decision-coach backend. It analyzes your played move against candidate moves and returns:

- best move by equity
- your move quality (`excellent`, `good`, `inaccuracy`, `mistake`, `blunder`)
- plain-language reasons based on structural/racing heuristics

This is an MVP foundation designed to plug into a stronger engine (e.g. GNU Backgammon) later.

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
- `POST /sessions`
- `GET /sessions/{session_id}`
- `POST /sessions/{session_id}/play-turn`
- `POST /sessions/{session_id}/ai-turn`
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
      "notation": "24/18 13/7",
      "steps": [
        {"from_point": 24, "to_point": 18},
        {"from_point": 13, "to_point": 7}
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
        "notation": "24/18 13/7",
        "steps": [
          {"from_point": 24, "to_point": 18},
          {"from_point": 13, "to_point": 7}
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
  -d '{ "initial_position": { ...position payload... } }'
```

Play a turn in that session (rate move, advance board, set next dice):

```bash
curl -X POST 'http://127.0.0.1:8000/sessions/1/play-turn' \
  -H 'Content-Type: application/json' \
  -d '{ "played_move": { ... }, "next_dice": [3,2], "record_training": true }'
```

Have AI choose and apply a turn in that session:

```bash
curl -X POST 'http://127.0.0.1:8000/sessions/1/ai-turn' \
  -H 'Content-Type: application/json' \
  -d '{ "next_dice": [4,2], "apply_move": true }'
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
curl 'http://127.0.0.1:8000/training/summary'
curl 'http://127.0.0.1:8000/training/mistakes?limit=20'
curl 'http://127.0.0.1:8000/training/leaks'
```

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

Optional:

```bash
export GAMMONDATOR_FALLBACK_TO_HEURISTIC=0
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

## Next Step

Replace the heuristic evaluator in `app/analysis.py` with an engine adapter (GNU Backgammon/XG-compatible bridge) while keeping the same response contract.
