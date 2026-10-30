"""Bounded local burst and health responsiveness; not a production capacity test."""

import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".runtime/acceptance"


async def main():
    data = (OUT / "scan.pdf").read_bytes()
    health = []
    done = asyncio.Event()
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:4000", timeout=60, limits=httpx.Limits(max_connections=64)
    ) as client:
        await client.get("/")

        async def monitor():
            while not done.is_set():
                start = time.perf_counter()
                response = await client.get("/api/health")
                assert response.status_code == 200
                health.append((time.perf_counter() - start) * 1000)
                await asyncio.sleep(0.01)

        monitor_task = asyncio.create_task(monitor())

        async def submit():
            return await client.post(
                "/api/editable",
                data={
                    "use_ocr": "true",
                    "ocr_language": "eng",
                    "ocr_dpi": "200",
                    "ocr_min_confidence": "20",
                },
                files={"file": ("scan.pdf", data, "application/pdf")},
            )

        responses = await asyncio.gather(*(submit() for _ in range(20)))
        done.set()
        await monitor_task
    statuses = [r.status_code for r in responses]
    assert set(statuses) <= {200, 503}, statuses
    assert 200 in statuses and 503 in statuses, statuses
    result = {
        "scope": "one local 20-request OCR burst, queue default8; no production capacity claim",
        "accepted": statuses.count(200),
        "busy_rejected": statuses.count(503),
        "health_samples": len(health),
        "health_median_ms": round(statistics.median(health), 3),
        "health_max_ms": round(max(health), 3),
    }
    (OUT / "bounded-load.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


asyncio.run(main())
