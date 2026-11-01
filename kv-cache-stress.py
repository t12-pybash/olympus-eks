#!/usr/bin/env python3
"""
KV cache stress test for vLLM.
Goal: saturate the KV cache by sending long-context requests with high concurrency.
Strategy: large system prompt + long response forces vLLM to hold many KV blocks per request.
"""

import asyncio
import time
import aiohttp
import json

VLLM_URL = "http://localhost:8000/v1/chat/completions"
MODEL = "TheBloke/Mistral-7B-Instruct-v0.2-AWQ"
CONCURRENCY = 32
DURATION_SECONDS = 180

# Very long input prompt to front-load KV cache blocks on prefill (~1500 tokens)
SYSTEM_PROMPT = " ".join(["Kubernetes is a container orchestration system."] * 150)

USER_PROMPT = """Given everything above, explain in exhaustive detail the operational differences
between GPU compute saturation and KV cache saturation in LLM inference, with specific
Prometheus alert rules, thresholds, and remediation steps for each."""

stats = {
    "completed": 0,
    "errors": 0,
    "ttfts": [],
    "e2e_latencies": [],
}

async def send_request(session: aiohttp.ClientSession, request_id: int):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": SYSTEM_PROMPT + "\n\n" + USER_PROMPT},
        ],
        "max_tokens": 4096,
        "stream": True,
    }

    start = time.perf_counter()
    ttft = None

    try:
        async with session.post(VLLM_URL, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            if resp.status != 200:
                stats["errors"] += 1
                print(f"[{request_id}] HTTP {resp.status}")
                return

            async for line in resp.content:
                line = line.decode().strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    if ttft is None and chunk["choices"][0]["delta"].get("content"):
                        ttft = time.perf_counter() - start
                except Exception:
                    continue

        e2e = time.perf_counter() - start
        stats["completed"] += 1
        if ttft:
            stats["ttfts"].append(ttft * 1000)
        stats["e2e_latencies"].append(e2e * 1000)
        print(f"[{request_id}] done — TTFT: {ttft*1000:.0f}ms, e2e: {e2e*1000:.0f}ms")

    except Exception as e:
        stats["errors"] += 1
        print(f"[{request_id}] error: {e}")


async def worker(session: aiohttp.ClientSession, worker_id: int, end_time: float):
    req_id = worker_id * 1000
    while time.time() < end_time:
        await send_request(session, req_id)
        req_id += 1


async def main():
    print(f"KV cache stress test — {CONCURRENCY} workers, {DURATION_SECONDS}s")
    print(f"System prompt + user prompt forces long KV cache occupancy per request")
    print("Watch: kubectl port-forward -n olympus svc/vllm 8000:8000")
    print("Metrics: curl http://localhost:8000/metrics | grep kv_cache\n")

    end_time = time.time() + DURATION_SECONDS

    connector = aiohttp.TCPConnector(limit=CONCURRENCY + 4)
    async with aiohttp.ClientSession(connector=connector) as session:
        workers = [worker(session, i, end_time) for i in range(CONCURRENCY)]
        await asyncio.gather(*workers)

    print("\n--- Results ---")
    print(f"Completed: {stats['completed']}")
    print(f"Errors:    {stats['errors']}")

    if stats["ttfts"]:
        ttfts = sorted(stats["ttfts"])
        n = len(ttfts)
        print(f"TTFT  p50: {ttfts[n//2]:.0f}ms  p95: {ttfts[int(n*0.95)]:.0f}ms  p99: {ttfts[int(n*0.99)]:.0f}ms")

    if stats["e2e_latencies"]:
        e2es = sorted(stats["e2e_latencies"])
        n = len(e2es)
        print(f"E2E   p50: {e2es[n//2]:.0f}ms  p95: {e2es[int(n*0.95)]:.0f}ms  p99: {e2es[int(n*0.99)]:.0f}ms")

    throughput = stats["completed"] / DURATION_SECONDS
    print(f"Throughput: {throughput:.2f} req/s")


if __name__ == "__main__":
    asyncio.run(main())
