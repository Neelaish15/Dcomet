import sys
import os
import asyncio
import hashlib
import hmac
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from threading import Thread, Lock
import time
import math
import random
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from collections import defaultdict, deque

# Import DcometSystem from project root main.py
from main import DcometSystem
from src.core.persistence import PersistenceStore

app = FastAPI()

# Allow CORS for frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

dcomet_system = None
simulation_thread = None
simulation_running = False
simulation_data = []
trading_state_lock = Lock()
persistence = PersistenceStore()
latest_snapshot = {
    "ts": datetime.now().isoformat(),
    "simulation_running": False,
    "cycles": 0,
    "trade_flow": "idle",
}

# Security and reliability settings.
API_KEY = os.getenv("DCOMET_API_KEY", "")
SIGNING_SECRET = os.getenv("DCOMET_SIGNING_SECRET", "dcomet-dev-secret")
RATE_LIMIT_PER_MINUTE = int(os.getenv("DCOMET_RATE_LIMIT_PER_MINUTE", "240"))
rate_limit_map: dict[str, deque] = defaultdict(deque)


class TradingOfferRequest(BaseModel):
    offer_id: str | None = None
    seller: str
    buyer: str
    energy_kwh: float
    price_usd: float
    time_block: str
    cycle: int | str | None = None


class ChatMessageRequest(BaseModel):
    sender: str = Field(default="bap", pattern="^(bap|bpp|system)$")
    text: str = Field(min_length=1, max_length=500)


def _rate_limit_guard(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = rate_limit_map[ip]
    while bucket and (now - bucket[0]) > 60:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket.append(now)


def _require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not API_KEY:
        return
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _verify_signature(payload: str, signature: str | None) -> None:
    if signature is None:
        return
    digest = hmac.new(SIGNING_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, signature):
        raise HTTPException(status_code=401, detail="Invalid payload signature")


def _idempotent_response_or_none(endpoint: str, key: str | None) -> dict | None:
    if not key:
        return None
    return persistence.get_idempotent_response(key, endpoint)


def _save_idempotent_response(endpoint: str, key: str | None, response: dict) -> None:
    if not key:
        return
    persistence.save_idempotent_response(key, endpoint, response)


def _new_trading_state() -> dict:
    return {
        "trade_flow": "idle",
        "payment_status": "not-started",
        "current_offer": None,
        "activity_log": [],
        "chat_messages": [],
        "updated_at": datetime.now().isoformat(),
    }


trading_state = _new_trading_state()


def _ui_time() -> str:
    return datetime.now().strftime("%I:%M:%S %p")


def _append_activity(message: str) -> None:
    trading_state["activity_log"] = [
        {
            "id": f"act-{time.time_ns()}",
            "message": message,
            "timestamp": _ui_time(),
        },
        *trading_state["activity_log"],
    ][:12]


def _append_chat(sender: str, text: str) -> None:
    trading_state["chat_messages"] = [
        *trading_state["chat_messages"],
        {
            "id": f"msg-{time.time_ns()}",
            "sender": sender,
            "text": text,
            "timestamp": _ui_time(),
        },
    ][-100:]


def _set_trade_flow(next_flow: str) -> None:
    trading_state["trade_flow"] = next_flow
    trading_state["updated_at"] = datetime.now().isoformat()


def _update_snapshot() -> None:
    latest_snapshot["ts"] = datetime.now().isoformat()
    latest_snapshot["simulation_running"] = simulation_running
    latest_snapshot["cycles"] = len(simulation_data)
    latest_snapshot["trade_flow"] = trading_state.get("trade_flow", "idle")


def _generate_virtual_excess_power(cycle_index: int) -> dict:
    """Generate virtual real-time excessive power profile using configured DER capacities."""
    cycle_phase = cycle_index + 1
    
    # Read actual DER capacities from config (3kW+)
    der_1_capacity = dcomet_system.config.get('der_config.der_1.rated_capacity_w', 3000.0)
    der_2_capacity = dcomet_system.config.get('der_config.der_2.rated_capacity_w', 4000.0)
    der_3_capacity = dcomet_system.config.get('der_config.der_3.rated_capacity_w', 5000.0)
    
    # Generate realistic solar curves for each DER
    # Solar profile: peak at midday, 0 at sunrise/sunset, varies by cloud conditions
    solar_altitude = max(0, math.sin((cycle_phase / 2.2)))  # 0 to 1, peaking mid-simulation
    
    # Individual DER outputs based on configured profiles
    der_1_power = der_1_capacity * max(0, solar_altitude + 0.15 * math.sin(cycle_phase / 1.3))  # sunny profile with variation
    der_2_power = der_2_capacity * max(0, solar_altitude * 0.95 + 0.05 * math.sin(cycle_phase / 1.8))  # variable with clouds
    der_3_power = der_3_capacity * 0.65  # steady profile (70% typical for midday steady)
    
    # Add realistic noise (±2% of capacity)
    der_1_power += random.uniform(-50, 50)
    der_2_power += random.uniform(-80, 80)
    der_3_power += random.uniform(-100, 100)
    
    der_1_power = max(0, der_1_power)
    der_2_power = max(0, der_2_power)
    der_3_power = max(0, der_3_power)
    
    total_generation_w = der_1_power + der_2_power + der_3_power
    
    # Demand: scale with installed capacity, typically 20-40% of total generation
    demand_w = max(1000, (total_generation_w * 0.3) + random.uniform(-500, 500))
    
    available_for_trading_w = max(0.0, total_generation_w * 0.7)
    excess_power_w = max(0.0, total_generation_w - demand_w)

    der_power_w = {
        "der_1": round(der_1_power, 3),
        "der_2": round(der_2_power, 3),
        "der_3": round(der_3_power, 3),
    }

    return {
        "timestamp": datetime.now().isoformat(),
        "total_generation_w": round(total_generation_w, 3),
        "demand_w": round(demand_w, 3),
        "available_for_trading_w": round(available_for_trading_w, 3),
        "excess_power_w": round(excess_power_w, 3),
        "der_power_w": der_power_w,
    }


def _get_15_min_block(base_time: datetime, cycle_index: int) -> dict:
    block_start = base_time + timedelta(minutes=15 * cycle_index)
    block_end = block_start + timedelta(minutes=15)
    return {
        "start": block_start.isoformat(),
        "end": block_end.isoformat(),
        "label": f"{block_start.strftime('%H:%M')} - {block_end.strftime('%H:%M')}",
    }


def _enrich_trade_with_kwh(trade: dict, time_block: dict) -> dict:
    trade_copy = dict(trade)

    # 15-minute dispatch interval energy conversion.
    if "quantity_wh" in trade_copy and trade_copy["quantity_wh"] is not None:
        energy_kwh = float(trade_copy["quantity_wh"]) / 1000.0
    else:
        quantity_w = float(trade_copy.get("quantity_w", 0.0))
        energy_kwh = (quantity_w * 0.25) / 1000.0

    trade_copy["energy_kwh"] = round(max(0.0, energy_kwh), 6)
    trade_copy["dispatch_interval_minutes"] = 15
    trade_copy["time_block"] = time_block
    return trade_copy

@app.on_event("startup")
def startup_event():
    global dcomet_system
    dcomet_system = DcometSystem()
    persistence.log_event("app.startup", {"status": "ok"})


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.get("/ready")
def ready():
    ready_state = dcomet_system is not None
    return JSONResponse(
        status_code=200 if ready_state else 503,
        content={"ready": ready_state, "simulation_running": simulation_running},
    )


@app.get("/metrics")
def metrics():
    ml_insights = dcomet_system.agent_manager.get_ml_insights() if dcomet_system else {}
    return {
        "simulation": {"running": simulation_running, "cycles": len(simulation_data)},
        "trading": {
            "trade_flow": trading_state.get("trade_flow", "idle"),
            "payment_status": trading_state.get("payment_status", "not-started"),
        },
        "ml": ml_insights,
    }

@app.post("/start_simulation")
def start_simulation(
    request: Request,
    num_cycles: int = 10,
    x_idempotency_key: str | None = Header(default=None),
    _auth: None = Depends(_require_api_key),
):
    global simulation_thread, simulation_running, simulation_data, trading_state
    _rate_limit_guard(request)
    reused = _idempotent_response_or_none("/start_simulation", x_idempotency_key)
    if reused is not None:
        return reused
    if simulation_running:
        return {"status": "already running"}
    simulation_data = []
    simulation_running = True
    with trading_state_lock:
        trading_state = _new_trading_state()
    persistence.log_event("simulation.started", {"num_cycles": num_cycles})
    _update_snapshot()

    now = datetime.now()
    base_dispatch_time = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)

    def run():
        global simulation_running, simulation_data
        for cycle in range(num_cycles):
            if not simulation_running:
                break

            time_block = _get_15_min_block(base_dispatch_time, cycle)
            trades = dcomet_system.run_trading_cycle(cycle)
            enriched_trades = [_enrich_trade_with_kwh(trade, time_block) for trade in trades]
            cycle_trade_kwh = round(sum(trade.get("energy_kwh", 0.0) for trade in enriched_trades), 6)
            telemetry = _generate_virtual_excess_power(cycle)
            explainability = [
                {
                    "trade_id": trade.get("trade_id"),
                    "explainability": trade.get("explainability", {}),
                }
                for trade in enriched_trades
            ]

            # Convert power values to energy for the 15-minute block.
            telemetry["available_for_trading_kwh"] = round((telemetry.get("available_for_trading_w", 0.0) * 0.25) / 1000.0, 6)
            telemetry["excess_power_kwh"] = round((telemetry.get("excess_power_w", 0.0) * 0.25) / 1000.0, 6)
            telemetry["generation_kwh"] = round((telemetry.get("total_generation_w", 0.0) * 0.25) / 1000.0, 6)
            telemetry["demand_kwh"] = round((telemetry.get("demand_w", 0.0) * 0.25) / 1000.0, 6)

            # Collect summary data for frontend
            simulation_data.append({
                "cycle": cycle + 1,
                "time_block": time_block,
                "trades": enriched_trades,
                "cycle_trade_volume_kwh": cycle_trade_kwh,
                "telemetry": telemetry,
                "explainability": explainability,
            })
            for trade in enriched_trades:
                persistence.upsert_trade(trade)
            persistence.log_event(
                "simulation.cycle",
                {
                    "cycle": cycle + 1,
                    "trade_count": len(enriched_trades),
                    "cycle_trade_volume_kwh": cycle_trade_kwh,
                },
            )
            _update_snapshot()
            time.sleep(dcomet_system.config.get('trading.trading_interval_seconds', 2))
        simulation_running = False
        persistence.log_event("simulation.stopped", {"cycles": len(simulation_data)})
        _update_snapshot()
    simulation_thread = Thread(target=run)
    simulation_thread.start()
    response = {"status": "started"}
    _save_idempotent_response("/start_simulation", x_idempotency_key, response)
    return response

@app.get("/simulation_status")
def simulation_status(request: Request):
    _rate_limit_guard(request)
    return {"running": simulation_running, "cycles": len(simulation_data)}

@app.get("/simulation_data")
def get_simulation_data(request: Request):
    _rate_limit_guard(request)
    return simulation_data

@app.post("/stop_simulation")
def stop_simulation(request: Request, _auth: None = Depends(_require_api_key)):
    global simulation_running
    _rate_limit_guard(request)
    simulation_running = False
    persistence.log_event("simulation.stop_requested", {})
    _update_snapshot()
    return {"status": "stopping"}


@app.get("/trading/state")
def get_trading_state(request: Request):
    _rate_limit_guard(request)
    with trading_state_lock:
        return {
            "trade_flow": trading_state["trade_flow"],
            "payment_status": trading_state["payment_status"],
            "current_offer": trading_state["current_offer"],
            "activity_log": trading_state["activity_log"],
            "chat_messages": trading_state["chat_messages"],
            "updated_at": trading_state["updated_at"],
        }


@app.post("/trading/reset")
def reset_trading_state(request: Request, _auth: None = Depends(_require_api_key)):
    global trading_state
    _rate_limit_guard(request)
    with trading_state_lock:
        trading_state = _new_trading_state()
        _update_snapshot()
    persistence.log_event("trading.reset", {})
    return {"status": "reset"}


@app.post("/trading/request")
async def trading_request(
    payload: TradingOfferRequest,
    request: Request,
    x_idempotency_key: str | None = Header(default=None),
    x_payload_signature: str | None = Header(default=None),
):
    _rate_limit_guard(request)
    raw = (await request.body()).decode("utf-8")
    _verify_signature(raw, x_payload_signature)
    reused = _idempotent_response_or_none("/trading/request", x_idempotency_key)
    if reused is not None:
        return reused
    with trading_state_lock:
        trading_state["current_offer"] = payload.model_dump()
        trading_state["payment_status"] = "not-started"
        _set_trade_flow("requested")
        _append_activity(
            f"BAP requested {payload.energy_kwh:.5f} kWh from {payload.seller}"
        )
        _append_chat(
            "bap",
            f"Hi {payload.seller}, requesting {payload.energy_kwh:.5f} kWh for {payload.time_block}.",
        )
        _append_chat("system", "Notification: Buyer request sent to seller app.")
        _update_snapshot()
    response = {"status": "ok", "trade_flow": "requested"}
    persistence.log_event("trading.request", payload.model_dump(), correlation_id=payload.offer_id)
    _save_idempotent_response("/trading/request", x_idempotency_key, response)
    return response


@app.post("/trading/accept")
def trading_accept(
    request: Request,
    x_idempotency_key: str | None = Header(default=None),
    _auth: None = Depends(_require_api_key),
):
    _rate_limit_guard(request)
    reused = _idempotent_response_or_none("/trading/accept", x_idempotency_key)
    if reused is not None:
        return reused
    with trading_state_lock:
        if trading_state["trade_flow"] != "requested":
            raise HTTPException(status_code=409, detail="Trade is not awaiting seller response")
        offer = trading_state["current_offer"] or {}
        _set_trade_flow("accepted")
        _append_activity(
            f"BPP accepted request for {float(offer.get('energy_kwh', 0.0)):.5f} kWh"
        )
        _append_chat("bpp", f"Request accepted. Dispatch locked for {offer.get('time_block', '--')}.")
        _append_chat("system", "Notification: Seller accepted. Proceed to dispatch and delivery confirmation.")
        _update_snapshot()
    response = {"status": "ok", "trade_flow": "accepted"}
    persistence.log_event("trading.accept", {"offer": trading_state.get("current_offer")})
    _save_idempotent_response("/trading/accept", x_idempotency_key, response)
    return response


@app.post("/trading/reject")
def trading_reject(
    request: Request,
    x_idempotency_key: str | None = Header(default=None),
    _auth: None = Depends(_require_api_key),
):
    _rate_limit_guard(request)
    reused = _idempotent_response_or_none("/trading/reject", x_idempotency_key)
    if reused is not None:
        return reused
    with trading_state_lock:
        if trading_state["trade_flow"] != "requested":
            raise HTTPException(status_code=409, detail="Trade is not awaiting seller response")
        _set_trade_flow("rejected")
        _append_activity("BPP rejected buyer request")
        _append_chat("bpp", "Unable to fulfill this block. Please choose another offer.")
        _append_chat("system", "Notification: Seller rejected current request.")
        _update_snapshot()
    response = {"status": "ok", "trade_flow": "rejected"}
    persistence.log_event("trading.reject", {"offer": trading_state.get("current_offer")})
    _save_idempotent_response("/trading/reject", x_idempotency_key, response)
    return response


@app.post("/trading/complete")
def trading_complete(
    request: Request,
    x_idempotency_key: str | None = Header(default=None),
):
    _rate_limit_guard(request)
    reused = _idempotent_response_or_none("/trading/complete", x_idempotency_key)
    if reused is not None:
        return reused
    with trading_state_lock:
        if trading_state["trade_flow"] != "accepted":
            raise HTTPException(status_code=409, detail="Trade has not been accepted yet")
        _set_trade_flow("completed")
        trading_state["payment_status"] = "pending"
        _append_activity("BAP confirmed receipt and closed dispatch")
        _append_chat("bap", "Energy received. Awaiting payment confirmation.")
        _append_chat("system", "Notification: Dispatch complete. Payment action available.")
        _update_snapshot()
    response = {"status": "ok", "trade_flow": "completed", "payment_status": "pending"}
    persistence.log_event("trading.complete", {"offer": trading_state.get("current_offer")})
    _save_idempotent_response("/trading/complete", x_idempotency_key, response)
    return response


@app.post("/trading/payment/confirm")
def trading_confirm_payment(
    request: Request,
    x_idempotency_key: str | None = Header(default=None),
    _auth: None = Depends(_require_api_key),
):
    _rate_limit_guard(request)
    reused = _idempotent_response_or_none("/trading/payment/confirm", x_idempotency_key)
    if reused is not None:
        return reused
    with trading_state_lock:
        if trading_state["trade_flow"] != "completed":
            raise HTTPException(status_code=409, detail="Trade must be completed before payment")
        if trading_state["payment_status"] == "paid":
            return {"status": "ok", "payment_status": "paid"}
        trading_state["payment_status"] = "paid"
        offer = trading_state["current_offer"] or {}
        _append_activity(
            f"Payment settled: ${float(offer.get('price_usd', 0.0)):.3f} to {offer.get('seller', 'seller')}"
        )
        _append_chat(
            "system",
            f"Payment successful: ${float(offer.get('price_usd', 0.0)):.3f} transferred.",
        )
        trading_state["updated_at"] = datetime.now().isoformat()
        _update_snapshot()
    response = {"status": "ok", "payment_status": "paid"}
    persistence.log_event("trading.payment.confirm", {"offer": trading_state.get("current_offer")})
    _save_idempotent_response("/trading/payment/confirm", x_idempotency_key, response)
    return response


@app.post("/trading/chat")
def trading_send_chat(payload: ChatMessageRequest, request: Request):
    _rate_limit_guard(request)
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message text cannot be empty")
    sender = payload.sender if payload.sender in {"bap", "bpp", "system"} else "bap"
    with trading_state_lock:
        _append_chat(sender, text)
        trading_state["updated_at"] = datetime.now().isoformat()
        _update_snapshot()
    persistence.log_event("trading.chat", {"sender": sender, "text": text[:120]})
    return {"status": "ok"}


@app.get("/events")
async def stream_events(request: Request):
    async def event_generator():
        last_seen_ts = ""
        while True:
            if await request.is_disconnected():
                break

            current_ts = latest_snapshot.get("ts", "")
            if current_ts != last_seen_ts:
                payload = {
                    "ts": current_ts,
                    "simulation_status": {"running": simulation_running, "cycles": len(simulation_data)},
                    "trading": {
                        "trade_flow": trading_state.get("trade_flow", "idle"),
                        "payment_status": trading_state.get("payment_status", "not-started"),
                    },
                    "latest_cycle": simulation_data[-1] if simulation_data else None,
                }
                yield f"data: {json.dumps(payload)}\n\n"
                last_seen_ts = current_ts

            await asyncio.sleep(0.8)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/audit/events")
def audit_events(request: Request, limit: int = 50, _auth: None = Depends(_require_api_key)):
    _rate_limit_guard(request)
    return persistence.recent_events(limit=max(1, min(200, limit)))


@app.get("/audit/trades")
def audit_trades(request: Request, limit: int = 50, _auth: None = Depends(_require_api_key)):
    _rate_limit_guard(request)
    return persistence.recent_trades(limit=max(1, min(200, limit)))
