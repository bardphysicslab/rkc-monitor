import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from raspi.drivers.esp32_door_temp_driver import Esp32DoorTempDriver


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "app_config.json"
EXAMPLE_CONFIG_PATH = BASE_DIR / "config" / "app_config.example.json"

app = FastAPI(title="RKC-Monitor")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def local_now() -> datetime:
    return utc_now().astimezone()


def load_config() -> Dict[str, Any]:
    config_path = Path(os.environ.get("BARDBOX_APP_CONFIG", DEFAULT_CONFIG_PATH))
    if not config_path.exists() and config_path == DEFAULT_CONFIG_PATH:
        config_path = EXAMPLE_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


APP_CONFIG = load_config()
APP_SETTINGS = APP_CONFIG.get("app", APP_CONFIG)


def load_drivers(config: Dict[str, Any]) -> List[Any]:
    loaded = []
    nodes = config.get("nodes", [])

    if not nodes:
        for entry in config.get("drivers", []):
            driver_config = entry.get("config", {})
            nodes.append(
                {
                    "uid": entry.get("uid", "bb-0000"),
                    "host": driver_config.get("host"),
                    "port": driver_config.get("port", 1234),
                    "timeout_s": driver_config.get("timeout_s", 1.0),
                }
            )

    for node in nodes:
        uid = node.get("uid", "bb-0000")
        host = node.get("host")
        if not host:
            raise ValueError(f"node {uid} requires host")

        loaded.append(
            Esp32DoorTempDriver(
                uid=uid,
                name=node.get("name"),
                location=node.get("location"),
                host=host,
                port=int(node.get("port", 1234)),
                timeout_s=float(node.get("timeout_s", 1.0)),
            )
        )

    return loaded


DRIVERS = load_drivers(APP_CONFIG)


def time_status() -> Dict[str, Any]:
    return {
        "valid": True,
        "source": "system",
        "sane": True,
        "ntp_synced": False,
    }


def latest_readings() -> List[Dict[str, Any]]:
    readings = []
    for driver in DRIVERS:
        try:
            readings.append(driver.get_reading())
        except Exception as exc:
            uid = getattr(driver, "uid", "unknown")
            readings.append(
                {
                    "uid": uid,
                    "timestamp": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "status": "error",
                    "data": {
                        "temp_c": None,
                        "door_open": None,
                        "door_alarm": None,
                    },
                    "extended": {
                        "uid": uid,
                        "name": getattr(driver, "name", uid),
                        "location": getattr(driver, "location", None),
                        "host": getattr(driver, "host", None),
                        "port": getattr(driver, "port", None),
                        "error": "driver_exception",
                        "detail": str(exc),
                    },
                    "raw": None,
                }
            )
    return readings


@app.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": APP_SETTINGS.get("title", "RKC Monitor"),
            "app_id": APP_SETTINGS.get("app_id", "bb-rkc-monitor"),
            "poll_interval_ms": APP_CONFIG.get(
                "poll_interval_ms",
                APP_SETTINGS.get("poll_interval_ms", 5000),
            ),
        },
    )


@app.get("/time")
def get_time():
    now_utc = utc_now()
    now_local = local_now()
    status = time_status()
    return JSONResponse(
        {
            "utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "local": now_local.strftime("%a %b %d, %H:%M:%S"),
            "local_tz": now_local.tzname(),
            "time_status": status,
        }
    )


@app.get("/app/info")
def get_app_info():
    return JSONResponse(
        {
            "app_id": APP_SETTINGS.get("app_id", "bb-rkc-monitor"),
            "title": APP_SETTINGS.get("title", "RKC Monitor"),
            "mode": APP_CONFIG.get("mode", APP_SETTINGS.get("mode", "sensor_monitor")),
            "node_count": len(DRIVERS),
            "driver_count": len(DRIVERS),
        }
    )


@app.get("/app/health")
def get_app_health():
    readings = latest_readings()
    degraded = any(reading.get("status") != "ok" for reading in readings)
    return JSONResponse(
        {
            "ok": not degraded,
            "status": "ok" if not degraded else "degraded",
            "time_status": time_status(),
            "node_count": len(DRIVERS),
            "driver_count": len(DRIVERS),
            "latest_readings": readings,
        }
    )


@app.get("/drivers")
def get_drivers():
    payload = []
    for driver in DRIVERS:
        try:
            info = driver.get_info()
        except Exception as exc:
            info = {
                "uid": getattr(driver, "uid", "unknown"),
                "source_type": "unknown",
                "transport": "tcp",
                "protocol": "bardbox",
                "firmware": None,
                "error": str(exc),
            }
        payload.append(
            {
                "info": info,
                "capabilities": driver.get_capabilities(),
            }
        )
    return JSONResponse({"drivers": payload})


@app.get("/readings/latest")
def get_latest_readings():
    return JSONResponse({"readings": latest_readings()})
