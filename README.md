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
- `POST /analyze-move`
- `POST /choose-ai-move`

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

## Next Step

Replace the heuristic evaluator in `app/analysis.py` with an engine adapter (GNU Backgammon/XG-compatible bridge) while keeping the same response contract.
