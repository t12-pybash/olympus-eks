"""
vLLM inference benchmark with W&B experiment tracking.

Sweeps serving configurations (concurrency, context length, output tokens)
and logs TTFT percentiles, throughput, KV cache peak, and GPU utilisation
to Weights & Biases for each run.

Usage:
    # Single run
    python benchmark.py --concurrent-workers 16 --max-tokens 1024 --prompt-length 512

    # Sweep (run after: wandb sweep sweep.yaml)
    wandb agent <sweep-id>
"""

import argparse
import statistics
import threading
import time

import requests
import wandb

VLLM_URL = "http://localhost:8000/v1/chat/completions"
PROMETHEUS_URL = "http://localhost:9090/api/v1/query"
MODEL = "mistralai/Mistral-7B-Instruct-v0.3"


def query_prometheus(metric: str) -> float:
    try:
        r = requests.get(PROMETHEUS_URL, params={"query": metric}, timeout=5)
        result = r.json()["data"]["result"]
        return float(result[0]["value"][1]) if result else 0.0
    except Exception:
        return 0.0


def single_request(prompt: str, max_tokens: int, results: list) -> None:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": True,
    }
    start = time.time()
    first_token = None
    try:
        with requests.post(VLLM_URL, json=payload, stream=True, timeout=120) as r:
            for chunk in r.iter_lines():
                if chunk and first_token is None:
                    first_token = time.time() - start
        if first_token is not None:
            results.append(first_token)
    except Exception:
        pass


def run_experiment(
    concurrent_workers: int,
    max_tokens: int,
    prompt_length: int,
    duration_s: int = 60,
) -> None:
    prompt = "Explain the following concept in detail: " + ("word " * prompt_length)

    wandb.init(
        project="vllm-inference-experiments",
        config={
            "concurrent_workers": concurrent_workers,
            "max_tokens": max_tokens,
            "prompt_length": prompt_length,
            "duration_s": duration_s,
            "model": MODEL,
        },
        reinit=True,
    )

    ttft_results: list[float] = []
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            single_request(prompt, max_tokens, ttft_results)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(concurrent_workers)]
    for t in threads:
        t.start()

    time.sleep(duration_s)
    stop.set()
    for t in threads:
        t.join(timeout=10)

    if len(ttft_results) < 5:
        print(f"Too few results ({len(ttft_results)}) — skipping W&B log")
        wandb.finish()
        return

    sorted_ttft = sorted(ttft_results)
    n = len(sorted_ttft)

    kv_peak = query_prometheus(
        f"max_over_time((vllm:gpu_cache_usage_perc or vector(0))[{duration_s}s:])"
    )
    gpu_util = query_prometheus(
        f"max_over_time(DCGM_FI_DEV_GPU_UTIL[{duration_s}s:])"
    )
    vram_free = query_prometheus(
        f"min_over_time(DCGM_FI_DEV_FB_FREE[{duration_s}s:])"
    )
    queue_peak = query_prometheus(
        f"max_over_time(vllm:num_requests_waiting[{duration_s}s:])"
    )

    wandb.log({
        "ttft_p50_ms":       sorted_ttft[n // 2] * 1000,
        "ttft_p95_ms":       sorted_ttft[int(n * 0.95)] * 1000,
        "ttft_p99_ms":       sorted_ttft[int(n * 0.99)] * 1000,
        "ttft_mean_ms":      statistics.mean(ttft_results) * 1000,
        "throughput_rps":    len(ttft_results) / duration_s,
        "kv_cache_peak_pct": kv_peak * 100,
        "gpu_util_peak_pct": gpu_util,
        "vram_free_min_mib": vram_free,
        "queue_peak":        queue_peak,
        "requests_completed": len(ttft_results),
    })

    print(
        f"workers={concurrent_workers} max_tokens={max_tokens} prompt_len={prompt_length} "
        f"| p95_ttft={sorted_ttft[int(n * 0.95)] * 1000:.0f}ms "
        f"| rps={len(ttft_results) / duration_s:.2f} "
        f"| kv_peak={kv_peak * 100:.1f}%"
    )

    wandb.finish()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrent-workers", type=int, default=16)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--prompt-length", type=int, default=512)
    parser.add_argument("--duration", type=int, default=60)
    args = parser.parse_args()

    run_experiment(
        concurrent_workers=args.concurrent_workers,
        max_tokens=args.max_tokens,
        prompt_length=args.prompt_length,
        duration_s=args.duration,
    )


if __name__ == "__main__":
    main()
