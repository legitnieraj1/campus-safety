#!/usr/bin/env python3
"""
SafetyHub Gateway — Bridges ESP32 sensor node to the Next.js backend.

Polls the ESP32's /api/data endpoint every 1 second and forwards
the sensor data to the Next.js /api/ingest endpoint via HTTP POST.

Usage:
    1. Connect your laptop WiFi to "Campus_Safety_System" (password: 12345678)
    2. Make sure the Next.js dev server is running (npm run dev)
    3. Run: python gateway.py

Environment variables (optional):
    ESP32_URL       - ESP32 API URL (default: http://192.168.4.1/api/data)
    BACKEND_URL     - Next.js backend URL (default: http://localhost:3000/api/ingest)
    API_KEY         - API key for backend auth (default: none)
    ZONE_ID         - Zone identifier (default: zone-a-engineering)
    ZONE_NAME       - Zone display name (default: Zone A - Engineering)
    POLL_INTERVAL   - Seconds between polls (default: 1)
"""

import os
import sys
import time
import json
import signal
import logging
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ─── Configuration ───

ESP32_URL     = os.getenv("ESP32_URL", "http://192.168.4.1/api/data")
# For local dev: http://localhost:3000/api/ingest
# For production: https://your-app.vercel.app/api/ingest
# For local dev: http://localhost:3000/api/ingest
# For production: https://campussafetysystemkgislhackathon.vercel.app/api/ingest
BACKEND_URL   = os.getenv("BACKEND_URL", "https://campussafetysystemkgislhackathon.vercel.app/api/ingest")
API_KEY       = os.getenv("API_KEY", "")
ZONE_ID       = os.getenv("ZONE_ID", "skasc-seminar-hall-1")
ZONE_NAME     = os.getenv("ZONE_NAME", "SKASC - Seminar Hall 1")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1"))

# ─── Logging ───

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gateway")

# ─── State ───

consecutive_esp_failures = 0
running = True


def signal_handler(sig, frame):
    global running
    log.info("Shutting down gateway...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def fetch_esp32():
    """Poll ESP32 /api/data endpoint. Returns parsed JSON or None."""
    global consecutive_esp_failures

    try:
        req = Request(ESP32_URL, method="GET")
        req.add_header("Accept", "application/json")
        with urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if consecutive_esp_failures > 0:
                log.info(f"ESP32 reconnected after {consecutive_esp_failures} failures")
            consecutive_esp_failures = 0
            return data
    except (URLError, HTTPError, json.JSONDecodeError, OSError) as e:
        consecutive_esp_failures += 1
        if consecutive_esp_failures <= 3 or consecutive_esp_failures % 10 == 0:
            log.warning(f"ESP32 unreachable ({consecutive_esp_failures}x): {e}")
        return None


def post_to_backend(sensor_data):
    """Forward sensor data to the Next.js /api/ingest endpoint."""
    payload = {
        "accelMag": sensor_data.get("accelMag", 0),
        "gasLevel": sensor_data.get("gasLevel", 0),
        "temperature": sensor_data.get("temperature", 0),
        "humidity": sensor_data.get("humidity", 0),
        "alert": sensor_data.get("alert", "System Normal"),
        "uptimeMs": sensor_data.get("uptimeMs", 0),
        "mpuAvailable": sensor_data.get("mpuAvailable", True),
        "motion": sensor_data.get("motion", False),
        "motionCount": sensor_data.get("motionCount", 0),
        "zoneId": ZONE_ID,
        "zoneName": ZONE_NAME,
        "gatewayTimestamp": datetime.now(timezone.utc).isoformat(),
    }

    body = json.dumps(payload).encode("utf-8")

    req = Request(BACKEND_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if API_KEY:
        req.add_header("Authorization", f"Bearer {API_KEY}")

    try:
        with urlopen(req, timeout=3) as resp:
            status = resp.status
            if status == 200:
                return True
            else:
                log.warning(f"Backend responded {status}")
                return False
    except (URLError, HTTPError, OSError) as e:
        log.error(f"Backend POST failed: {e}")
        return False


def post_offline_status():
    """Notify backend that ESP32 sensors are offline."""
    payload = {
        "accelMag": 0,
        "gasLevel": 0,
        "temperature": 0,
        "humidity": 0,
        "alert": "Sensor Offline",
        "uptimeMs": 0,
        "mpuAvailable": False,
        "motion": False,
        "motionCount": 0,
        "zoneId": ZONE_ID,
        "zoneName": ZONE_NAME,
        "gatewayTimestamp": datetime.now(timezone.utc).isoformat(),
    }

    body = json.dumps(payload).encode("utf-8")
    req = Request(BACKEND_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if API_KEY:
        req.add_header("Authorization", f"Bearer {API_KEY}")

    try:
        with urlopen(req, timeout=3):
            pass
    except (URLError, HTTPError, OSError):
        pass


def main():
    log.info("=" * 50)
    log.info("  SafetyHub Gateway v1.0")
    log.info("=" * 50)
    log.info(f"  ESP32 URL:   {ESP32_URL}")
    log.info(f"  Backend URL: {BACKEND_URL}")
    log.info(f"  Zone:        {ZONE_NAME} ({ZONE_ID})")
    log.info(f"  Interval:    {POLL_INTERVAL}s")
    log.info(f"  API Key:     {'set' if API_KEY else 'not set'}")
    log.info("=" * 50)
    log.info("Starting polling loop... (Ctrl+C to stop)\n")

    offline_notified = False

    while running:
        start = time.monotonic()

        sensor_data = fetch_esp32()

        if sensor_data:
            offline_notified = False
            success = post_to_backend(sensor_data)
            if success:
                mag = sensor_data.get("accelMag", 0)
                gas = sensor_data.get("gasLevel", 0)
                temp = sensor_data.get("temperature", 0)
                hum = sensor_data.get("humidity", 0)
                alert = sensor_data.get("alert", "")
                log.info(
                    f"Mag:{mag:.2f}G  Gas:{gas}  Temp:{temp:.1f}C  "
                    f"Hum:{hum:.1f}%  Alert:{alert}"
                )
        else:
            # ESP32 offline — notify backend after 10 consecutive failures
            if consecutive_esp_failures >= 10 and not offline_notified:
                post_offline_status()
                offline_notified = True
                log.warning("Sent offline status to backend")

        # Sleep for the remaining interval
        elapsed = time.monotonic() - start
        sleep_time = max(0, POLL_INTERVAL - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

    log.info("Gateway stopped.")


if __name__ == "__main__":
    main()
