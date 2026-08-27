"""Unit tests for env_server.json_action_to_native.

The gateway (mua-gateway) forwards actions in mobile_world's ``JSONAction``
schema; ``env_server.json_action_to_native`` is the single adapter that maps
that schema onto mobile_gym's native ``ActionType`` space. These tests pin the
mapping so a future drift in either side's field names is caught here rather
than in a live run.

Two layers of coverage:

1. ``test_*`` fed hand-built dicts — the concrete shapes the adapter must
   accept (including legacy ``x2/y2`` aliases).
2. ``test_contract_*`` fed ``JSONAction(**payload).model_dump()`` — proves the
   adapter consumes exactly what the gateway serializes. Skipped when
   mua-gateway is not importable (it lives in a sibling repo, not on the path
   in every environment).
"""

from __future__ import annotations

import pytest

from bench_env.env.base import ActionType
from bench_env.server.env_server import json_action_to_native


# ── mobile_world JSONAction (optional; sibling repo) ────────────────────────
# ``env`` is a top-level package inside mua-gateway, not on the path in every
# environment. ``find_spec`` can't be used here because it raises (rather than
# returning None) when the *parent* package ``env`` is missing entirely.

try:
    from env.mobile_world_json_action import JSONAction  # type: ignore

    _HAS_JSONACTION = True
except Exception:  # pragma: no cover - depends on sibling repo being on path
    JSONAction = None  # type: ignore
    _HAS_JSONACTION = False


def _via_contract(payload: dict) -> dict:
    """Round-trip a payload through mobile_world's JSONAction serializer."""
    return JSONAction(**payload).model_dump()


# ── Point / tap family ──────────────────────────────────────────────────────


def test_click():
    a = json_action_to_native({"action_type": "click", "x": 100, "y": 200})
    assert a is not None
    assert a.action_type == ActionType.CLICK
    assert a.data == {"point": [100, 200]}


def test_click_missing_coords_raises():
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        json_action_to_native({"action_type": "click"})


def test_double_tap():
    a = json_action_to_native({"action_type": "double_tap", "x": 10, "y": 20})
    assert a.action_type == ActionType.DOUBLE_TAP
    assert a.data == {"point": [10, 20]}


def test_long_press():
    a = json_action_to_native({"action_type": "long_press", "x": 30, "y": 40})
    assert a.action_type == ActionType.LONG_PRESS
    assert a.data == {"point": [30, 40]}


# ── Text input ───────────────────────────────────────────────────────────────


def test_input_text_basic_clears_by_default():
    # Default is clear-then-type: no clear_text field => clear=True.
    a = json_action_to_native({"action_type": "input_text", "text": "hello"})
    assert a.action_type == ActionType.TYPE
    assert a.data == {"value": "hello", "clear": True}


def test_input_text_with_clear_explicit_true():
    a = json_action_to_native(
        {"action_type": "input_text", "text": "hi", "clear_text": True}
    )
    assert a.data == {"value": "hi", "clear": True}


def test_input_text_clear_false_appends():
    # Only an explicit clear_text=False opts out of clearing (append mode).
    a = json_action_to_native(
        {"action_type": "input_text", "text": "hi", "clear_text": False}
    )
    assert a.data == {"value": "hi", "clear": False}


def test_input_text_with_point():
    a = json_action_to_native(
        {"action_type": "input_text", "text": "hi", "x": 5, "y": 6}
    )
    assert a.data == {"value": "hi", "clear": True, "point": [5, 6]}


# ── Keys / navigation ────────────────────────────────────────────────────────


def test_keyboard_enter():
    a = json_action_to_native({"action_type": "keyboard_enter"})
    assert a.action_type == ActionType.ENTER


def test_navigate_back():
    a = json_action_to_native({"action_type": "navigate_back"})
    assert a.action_type == ActionType.BACK


def test_navigate_home():
    a = json_action_to_native({"action_type": "navigate_home"})
    assert a.action_type == ActionType.HOME


def test_open_app():
    a = json_action_to_native({"action_type": "open_app", "app_name": "wechat"})
    assert a.action_type == ActionType.AWAKE
    assert a.data == {"value": "wechat"}


# ── Scroll (direction only) ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "direction,expected",
    [
        ("up", ([500, 300], [500, 700])),
        ("down", ([500, 700], [500, 300])),
        ("left", ([300, 500], [700, 500])),
        ("right", ([700, 500], [300, 500])),
    ],
)
def test_scroll_directions(direction, expected):
    a = json_action_to_native({"action_type": "scroll", "direction": direction})
    assert a.action_type == ActionType.SWIPE
    assert a.data == {"point1": expected[0], "point2": expected[1]}


def test_scroll_default_direction_is_down():
    a = json_action_to_native({"action_type": "scroll"})
    assert a.data == {"point1": [500, 700], "point2": [500, 300]}


# ── Swipe / drag (endpoint coords) ───────────────────────────────────────────


def test_swipe_start_end_coords():
    # mobile_world contract: start_x/start_y -> end_x/end_y
    a = json_action_to_native(
        {
            "action_type": "swipe",
            "start_x": 100,
            "start_y": 800,
            "end_x": 100,
            "end_y": 200,
        }
    )
    assert a.action_type == ActionType.SWIPE
    assert a.data == {"point1": [100, 800], "point2": [100, 200]}


def test_swipe_falls_back_to_direction():
    a = json_action_to_native({"action_type": "swipe", "direction": "up"})
    assert a.data == {"point1": [500, 300], "point2": [500, 700]}


def test_drag_start_end_coords():
    a = json_action_to_native(
        {
            "action_type": "drag",
            "start_x": 100,
            "start_y": 200,
            "end_x": 300,
            "end_y": 400,
        }
    )
    assert a.action_type == ActionType.DRAG
    assert a.data == {"point1": [100, 200], "point2": [300, 400]}


def test_drag_legacy_x2y2_alias():
    # hand-built dicts / older callers may still send x/y + x2/y2
    a = json_action_to_native(
        {"action_type": "drag", "x": 1, "y": 2, "x2": 3, "y2": 4}
    )
    assert a.data == {"point1": [1, 2], "point2": [3, 4]}


def test_drag_missing_end_raises():
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        json_action_to_native({"action_type": "drag", "start_x": 1, "start_y": 2})


# ── Wait / answer ────────────────────────────────────────────────────────────


def test_wait_default():
    a = json_action_to_native({"action_type": "wait"})
    assert a.action_type == ActionType.WAIT
    assert a.data == {"value": 1.0}


def test_answer():
    a = json_action_to_native({"action_type": "answer", "text": "42"})
    assert a.action_type == ActionType.ANSWER
    assert a.data == {"value": "42"}


# ── Terminal actions (status / finished) ─────────────────────────────────────


def test_status_complete_by_default():
    a = json_action_to_native({"action_type": "status", "text": "done"})
    assert a.action_type == ActionType.COMPLETE
    assert a.data == {"return": "done"}


def test_status_infeasible_is_abort():
    a = json_action_to_native(
        {"action_type": "status", "goal_status": "infeasible", "text": "cannot"}
    )
    assert a.action_type == ActionType.ABORT
    assert a.data == {"value": "cannot"}


def test_finished_maps_to_complete():
    a = json_action_to_native({"action_type": "finished"})
    assert a.action_type == ActionType.COMPLETE


# ── No-op / unsupported ──────────────────────────────────────────────────────


@pytest.mark.parametrize("at", ["", "unknown", "noop", "ask_user", "mcp"])
def test_noop_action_types_return_none(at):
    assert json_action_to_native({"action_type": at}) is None


# ── Contract round-trip (requires mua-gateway on path) ───────────────────────


@pytest.mark.skipif(not _HAS_JSONACTION, reason="mua-gateway not importable")
class TestContract:
    """Feed the adapter exactly what JSONAction.model_dump() produces."""

    def test_contract_click(self):
        a = json_action_to_native(_via_contract({"action_type": "click", "x": 1, "y": 2}))
        assert a.action_type == ActionType.CLICK
        assert a.data == {"point": [1, 2]}

    def test_contract_input_text_clear(self):
        a = json_action_to_native(
            _via_contract({"action_type": "input_text", "text": "x", "clear_text": True})
        )
        assert a.data == {"value": "x", "clear": True}

    def test_contract_input_text_default_clears(self):
        # JSONAction.clear_text defaults to None; the adapter treats
        # "not explicitly False" as clear=True.
        a = json_action_to_native(
            _via_contract({"action_type": "input_text", "text": "x"})
        )
        assert a.data == {"value": "x", "clear": True}

    def test_contract_input_text_explicit_false_appends(self):
        a = json_action_to_native(
            _via_contract({"action_type": "input_text", "text": "x", "clear_text": False})
        )
        assert a.data == {"value": "x", "clear": False}

    def test_contract_scroll(self):
        a = json_action_to_native(
            _via_contract({"action_type": "scroll", "direction": "up"})
        )
        assert a.data == {"point1": [500, 300], "point2": [500, 700]}

    def test_contract_swipe_uses_start_end(self):
        # The whole point of this suite: JSONAction serializes start_x/start_y/
        # end_x/end_y (never x2/y2), and the adapter must read those.
        payload = _via_contract(
            {
                "action_type": "swipe",
                "start_x": 100,
                "start_y": 800,
                "end_x": 100,
                "end_y": 200,
            }
        )
        assert "x2" not in payload and "end_x" in payload
        a = json_action_to_native(payload)
        assert a.data == {"point1": [100, 800], "point2": [100, 200]}

    def test_contract_drag_uses_start_end(self):
        payload = _via_contract(
            {
                "action_type": "drag",
                "start_x": 1,
                "start_y": 2,
                "end_x": 3,
                "end_y": 4,
            }
        )
        a = json_action_to_native(payload)
        assert a.data == {"point1": [1, 2], "point2": [3, 4]}

    def test_contract_open_app(self):
        a = json_action_to_native(
            _via_contract({"action_type": "open_app", "app_name": "Settings"})
        )
        assert a.action_type == ActionType.AWAKE
        assert a.data == {"value": "Settings"}

    def test_contract_status_infeasible(self):
        a = json_action_to_native(
            _via_contract(
                {"action_type": "status", "goal_status": "infeasible", "text": "no"}
            )
        )
        assert a.action_type == ActionType.ABORT
