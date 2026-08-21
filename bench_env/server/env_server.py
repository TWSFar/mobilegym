#!/usr/bin/env python3
"""Thin HTTP adapter exposing a single MobileGym device to the UIAgent gateway.

MobileGym itself is an in-process, Playwright-driven library (``MobileGymEnv`` +
``TaskRegistry``); it ships no gateway-compatible service. This module wraps one
``MobileGymEnv`` instance behind the exact HTTP contract that the gateway's
``AsyncMobileGymEnvClient`` (``mua-gateway/env/async_mobile_gym_env.py``) speaks:

    POST /init                 -> {"status": "ok"}
    GET  /screenshot           -> {"b64_png": <base64 jpeg>, "app_name": str}
    POST /step                 -> {"status": "ok"}
    POST /task/init            -> {"status": "ok"}
    POST /task/tear_down       -> {"status": "ok"}
    GET  /task/eval            -> {"score": float, "reason": str}
    GET  /task/goal            -> "<instruction string>"
    GET  /task/complexity      -> <float>
    GET  /task/list            -> [{"name": "suite.TaskName"}, ...]
    GET  /health               -> {"ok": bool}

One server process == one device (the gateway registers a device by URL). The
gateway drives the screenshot -> action loop externally, so this adapter holds
per-device state (env instance, current task, init/last observation) and MUST
NOT use ``Controller.run_loop``.

The env is built with ``coord_space="norm_0_1000"`` so the gateway's normalized
0-1000 coordinates map to physical pixels automatically inside ``_parse_point``.

Run:
    python -m bench_env.server.env_server --port 8100
    # or
    uvicorn bench_env.server.env_server:app --host 0.0.0.0 --port 8100

This process is a pure per-device adapter: it does NOT heartbeat or register
itself. The batch launcher (bench_env/server/start_gateway_device.sh) starts N
adapters on sequential ports and runs a single host-side loop that POSTs
{"environment":"mobile_gym","url":...} to the gateway's /heartbeat per port,
mirroring how mobile_world devices register.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import os
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from bench_env.env import MobileGymEnv
from bench_env.env.base import Action, ActionType, Observation
from bench_env.task.judge import JudgeInput
from bench_env.task.registry import TaskRegistry

# ── Config (env-overridable) ──────────────────────────────────────────────

# URL of the mobile-gym simulator/static frontend that MobileGymEnv navigates.
# The bench harness conventionally serves the frontend on :3000 (Vite dev) or
# behind nginx (dist/); point this at whatever serves the built app.
ENV_URL = os.getenv("MOBILEGYM_ENV_URL", "http://127.0.0.1:3000")
HEADLESS = os.getenv("MOBILEGYM_HEADLESS", "1") not in ("0", "false", "False", "")
PROXY = os.getenv("MOBILEGYM_PROXY") or None
# Pixel-7 defaults, kept in sync with factory.create_env / EnvPool.
VIEWPORT = (360, 800)
PHYSICAL_SIZE = (1080, 2400)
DEVICE_SCALE_FACTOR = 3

# Heartbeat / device registration is NOT done here — the batch launcher
# (bench_env/server/start_gateway_device.sh) POSTs /heartbeat per adapter port,
# mirroring mobile_world. This process is a pure per-device adapter.

# Difficulty label -> a numeric complexity the gateway can sort/threshold on.
_DIFFICULTY_SCORE = {"L1": 1.0, "L2": 2.0, "L3": 3.0, "L4": 4.0}


# ── Request models (match AsyncMobileGymEnvClient payloads) ────────────────


class InitRequest(BaseModel):
    device: str = "mobile_gym"


class StepRequest(BaseModel):
    device: str = "mobile_gym"
    action: dict[str, Any]


class TaskInitRequest(BaseModel):
    task_name: str
    req_device: str = "mobile_gym"


class TaskOpRequest(BaseModel):
    task_name: str
    req_device: str = "mobile_gym"


# ── Per-device state ───────────────────────────────────────────────────────


class DeviceState:
    """Holds the single MobileGymEnv instance and current task context."""

    def __init__(self) -> None:
        self.env: Optional[MobileGymEnv] = None
        self.registry = TaskRegistry()
        self.lock = asyncio.Lock()
        self.current_task: Any = None
        self.current_task_id: Optional[str] = None
        self.init_obs: Optional[Observation] = None
        self.last_obs: Optional[Observation] = None

    async def ensure_env(self) -> MobileGymEnv:
        if self.env is None:
            env = MobileGymEnv(
                url=ENV_URL,
                headless=HEADLESS,
                proxy=PROXY,
                coord_space="norm_0_1000",
                viewport_size=VIEWPORT,
                physical_size=PHYSICAL_SIZE,
                device_scale_factor=DEVICE_SCALE_FACTOR,
                verbose=False,
            )
            await env.start()
            self.env = env
        return self.env


STATE = DeviceState()


# ── JSONAction (gateway) -> native Action translation ──────────────────────


def _point(action: dict, *keys: str) -> Optional[list[int]]:
    """Build a [x, y] point (0-1000 space) from the given key pair, if present."""
    kx, ky = keys
    x, y = action.get(kx), action.get(ky)
    if x is None or y is None:
        return None
    return [int(x), int(y)]


# Gateway scroll direction -> a swipe vector in 0-1000 normalized space.
# A "scroll down" reveals content further down => finger swipes UP (high y -> low y).
_SCROLL_SWIPE = {
    "up": ([500, 300], [500, 700]),
    "down": ([500, 700], [500, 300]),
    "left": ([300, 500], [700, 500]),
    "right": ([700, 500], [300, 500]),
}


def json_action_to_native(action: dict) -> Optional[Action]:
    """Translate a gateway JSONAction dict into a native mobile-gym ``Action``.

    Returns ``None`` for no-op / unsupported action types (the env simply
    re-observes). Raises HTTPException(400) on malformed required fields.
    """
    at = str(action.get("action_type", "")).lower()

    if at in ("click", "tap"):
        p = _point(action, "x", "y")
        if p is None:
            raise HTTPException(400, "click requires x,y")
        return Action.click(p)

    if at == "double_tap":
        p = _point(action, "x", "y")
        if p is None:
            raise HTTPException(400, "double_tap requires x,y")
        return Action(ActionType.DOUBLE_TAP, {"point": p})

    if at == "long_press":
        p = _point(action, "x", "y")
        if p is None:
            raise HTTPException(400, "long_press requires x,y")
        return Action(ActionType.LONG_PRESS, {"point": p})

    if at in ("input_text", "type"):
        text = action.get("text", action.get("value", ""))
        p = _point(action, "x", "y")  # optional target field
        return Action.type_text(str(text), point=p)

    if at == "keyboard_enter":
        return Action(ActionType.ENTER, {})

    if at in ("navigate_back", "back"):
        return Action.back()

    if at in ("navigate_home", "home"):
        return Action.home()

    if at == "open_app":
        app = action.get("app_name", action.get("text", ""))
        return Action.awake(str(app))

    if at == "scroll":
        direction = str(action.get("direction", "down")).lower()
        p1, p2 = _SCROLL_SWIPE.get(direction, _SCROLL_SWIPE["down"])
        return Action.swipe(p1, p2)

    if at == "swipe":
        p1 = _point(action, "x", "y")
        p2 = _point(action, "x2", "y2")
        if p1 and p2:
            return Action.swipe(p1, p2)
        # Fall back to a directional swipe if only a direction was given.
        direction = str(action.get("direction", "down")).lower()
        d1, d2 = _SCROLL_SWIPE.get(direction, _SCROLL_SWIPE["down"])
        return Action.swipe(d1, d2)

    if at == "drag":
        p1 = _point(action, "x", "y") or _point(action, "x1", "y1")
        p2 = _point(action, "x2", "y2")
        if p1 is None or p2 is None:
            raise HTTPException(400, "drag requires start and end points")
        return Action(ActionType.DRAG, {"point1": p1, "point2": p2})

    if at == "wait":
        seconds = action.get("time", action.get("value", 1.0))
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            seconds = 1.0
        return Action.wait(seconds)

    if at == "answer":
        return Action.answer(str(action.get("text", action.get("value", ""))))

    # Terminal actions. The client collapses finished/terminate -> "status".
    if at in ("status", "finished", "terminate", "complete", "abort"):
        goal_status = str(action.get("goal_status", "")).lower()
        text = action.get("text", action.get("value", action.get("return", "")))
        if at == "abort" or goal_status in ("infeasible", "failed", "fail"):
            return Action.abort(str(text))
        return Action.complete(str(text))

    if at in ("", "unknown", "noop", "ask_user"):
        return None

    # Unknown/unsupported: no-op so a single bad action doesn't kill the loop.
    return None


# ── App-scoped lifespan (browser cleanup on shutdown) ──────────────────────


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        if STATE.env is not None:
            with contextlib.suppress(Exception):
                await STATE.env.close()


app = FastAPI(title="MobileGym Env Adapter", lifespan=lifespan)


# ── Endpoints ───────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict:
    # Healthy once the server is up; a live browser is created lazily on /init.
    ok = STATE.env is None or getattr(STATE.env, "page", None) is not None
    return {"ok": bool(ok)}


@app.post("/init")
async def init(_: InitRequest) -> dict:
    async with STATE.lock:
        await STATE.ensure_env()
    return {"status": "ok"}


@app.get("/screenshot")
async def screenshot(device: str = "mobile_gym", return_b64: bool = False) -> dict:
    async with STATE.lock:
        env = await STATE.ensure_env()
        obs = await env.get_observation()
        STATE.last_obs = obs
    b64 = base64.b64encode(obs.get_screenshot_bytes()).decode("ascii")
    return {"b64_png": b64, "app_name": obs.current_app or "未知"}


@app.post("/step")
async def step(req: StepRequest) -> dict:
    async with STATE.lock:
        env = await STATE.ensure_env()
        native = json_action_to_native(req.action)
        if native is not None:
            await env.step(native)
        # step()'s observation omits state; re-observe with full state so the
        # judge (which diffs init vs last state) has what it needs.
        STATE.last_obs = await env.get_observation()
    return {"status": "ok"}


@app.post("/task/init")
async def task_init(req: TaskInitRequest) -> dict:
    async with STATE.lock:
        env = await STATE.ensure_env()
        try:
            task_cls = STATE.registry.get_by_id(req.task_name)
        except ValueError as e:
            raise HTTPException(404, str(e))
        task = task_cls()
        init_obs = await task.setup(env)
        STATE.current_task = task
        STATE.current_task_id = req.task_name
        STATE.init_obs = init_obs
        STATE.last_obs = init_obs
    return {"status": "ok"}


@app.post("/task/tear_down")
async def task_tear_down(req: TaskOpRequest) -> dict:
    async with STATE.lock:
        task = STATE.current_task
        env = STATE.env
        if task is not None and env is not None:
            with contextlib.suppress(Exception):
                task.teardown(env)
        STATE.current_task = None
        STATE.current_task_id = None
        STATE.init_obs = None
    return {"status": "ok"}


@app.get("/task/eval")
async def task_eval(task_name: str, req_device: str = "mobile_gym") -> dict:
    async with STATE.lock:
        task = STATE.current_task
        env = STATE.env
        if task is None or STATE.init_obs is None:
            raise HTTPException(409, "No task initialized for this device")
        # Ensure last_obs carries current state (agent may not have stepped).
        last_obs = STATE.last_obs
        if env is not None:
            last_obs = await env.get_observation()
            STATE.last_obs = last_obs
        answer = env.agent_answer if env is not None else None

    judge_input = JudgeInput(init_obs=STATE.init_obs, last_obs=last_obs, answer=answer)
    result = task.evaluate(judge_input)

    score = 1.0 if result.passed else float(result.progress)
    reasons: list[str] = []
    if result.judge_error:
        reasons.append(f"judge_error: {result.judge_error}")
    for issue in result.issues:
        reasons.append(str(issue.get("reason") or issue))
    if not result.clean:
        for w in result.warnings[:5]:
            reasons.append(f"unexpected change: {w.get('path', w)}")
    reason = "; ".join(r for r in reasons if r) or ("passed" if result.passed else "not passed")
    return {"score": score, "reason": reason}


@app.get("/task/goal")
async def task_goal(task_name: str) -> str:
    try:
        task_cls = STATE.registry.get_by_id(task_name)
    except ValueError as e:
        raise HTTPException(404, str(e))
    # Prefer the live task instance (rendered params) if it matches.
    if STATE.current_task is not None and STATE.current_task_id == task_name:
        return STATE.current_task.description
    return task_cls().description


@app.get("/task/complexity")
async def task_complexity(task_name: str) -> float:
    try:
        task_cls = STATE.registry.get_by_id(task_name)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _DIFFICULTY_SCORE.get(getattr(task_cls, "difficulty", "L1"), 1.0)


@app.get("/task/list")
async def task_list() -> list[dict]:
    names: list[str] = []
    for suite in STATE.registry.list_suites(include_generated=False):
        for name in STATE.registry.list_tasks(suite):
            names.append(f"{suite}.{name}")
    return [{"name": n} for n in names]


# ── Entrypoint ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="MobileGym env adapter server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
