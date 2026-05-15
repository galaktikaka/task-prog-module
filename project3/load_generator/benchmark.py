#!/usr/bin/env python3
"""
Единый нагрузочный генератор для трёх стратегий кеширования.
Одинаковые профили (read_heavy / balanced / write_heavy) и метрики для всех.
"""

import argparse
import asyncio
import csv
import json
import random
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

import httpx

STRATEGIES = {
    "cache_aside": "http://localhost:8001",
    "write_through": "http://localhost:8002",
    "write_back": "http://localhost:8003",
}

PROFILES = {
    "read_heavy": 0.80,
    "balanced": 0.50,
    "write_heavy": 0.20,
}


@dataclass
class RunResult:
    strategy: str
    profile: str
    duration_s: int
    target_rps: int
    total_requests: int
    read_requests: int
    write_requests: int
    errors: int
    throughput_rps: float
    avg_latency_ms: float
    p95_latency_ms: float
    db_reads: int
    db_writes: int
    db_total: int
    cache_hit_rate_pct: float
    write_back_flushes: int
    write_back_flushed_items: int


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = min(len(sorted_vals) - 1, max(0, int(len(sorted_vals) * p / 100) - 1))
    return sorted_vals[idx]


async def wait_healthy(client: httpx.AsyncClient, base_url: str, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = await client.get(f"{base_url}/health", timeout=2.0)
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError(f"Service not healthy: {base_url}")


async def run_profile(
    strategy: str,
    base_url: str,
    profile: str,
    read_ratio: float,
    duration_s: int,
    target_rps: int,
    item_pool: int,
    workers: int,
) -> RunResult:
    latencies: List[float] = []
    errors = 0
    reads = 0
    writes = 0
    stop_at = time.time() + duration_s
    interval = 1.0 / target_rps if target_rps > 0 else 0

    async with httpx.AsyncClient(timeout=10.0) as client:
        await wait_healthy(client, base_url)
        await client.post(f"{base_url}/admin/reset-metrics")
        if strategy == "write_back":
            await client.post(f"{base_url}/admin/flush")

        async def worker(worker_id: int) -> None:
            nonlocal errors, reads, writes
            rng = random.Random(worker_id + int(time.time()))
            next_tick = time.time()
            while time.time() < stop_at:
                now = time.time()
                if now < next_tick:
                    await asyncio.sleep(min(0.001, next_tick - now))
                    continue
                next_tick += interval

                item_id = rng.randint(1, item_pool)
                is_read = rng.random() < read_ratio
                t0 = time.perf_counter()
                try:
                    if is_read:
                        r = await client.get(f"{base_url}/items/{item_id}")
                        reads += 1
                    else:
                        value = f"w-{strategy}-{int(time.time() * 1000) % 100000}"
                        r = await client.put(f"{base_url}/items/{item_id}", json={"value": value})
                        writes += 1
                    if r.status_code >= 400:
                        errors += 1
                    else:
                        latencies.append((time.perf_counter() - t0) * 1000)
                except httpx.HTTPError:
                    errors += 1

        tasks = [asyncio.create_task(worker(i)) for i in range(workers)]
        await asyncio.gather(*tasks)

        if strategy == "write_back":
            await asyncio.sleep(3)
            await client.post(f"{base_url}/admin/flush")

        metrics_resp = await client.get(f"{base_url}/metrics")
        metrics_resp.raise_for_status()
        m = metrics_resp.json()

    total = reads + writes
    elapsed = duration_s
    return RunResult(
        strategy=strategy,
        profile=profile,
        duration_s=duration_s,
        target_rps=target_rps,
        total_requests=total,
        read_requests=reads,
        write_requests=writes,
        errors=errors,
        throughput_rps=round(total / elapsed, 2),
        avg_latency_ms=round(statistics.mean(latencies), 2) if latencies else 0.0,
        p95_latency_ms=round(percentile(latencies, 95), 2),
        db_reads=m.get("db_reads", 0),
        db_writes=m.get("db_writes", 0),
        db_total=m.get("db_total", 0),
        cache_hit_rate_pct=m.get("cache_hit_rate_pct", 0.0),
        write_back_flushes=m.get("write_back_flushes", 0),
        write_back_flushed_items=m.get("write_back_flushed_items", 0),
    )


def print_result(r: RunResult) -> None:
    print(
        f"[{r.strategy:14}] profile={r.profile:12} "
        f"req={r.total_requests:5} thr={r.throughput_rps:7.1f} rps "
        f"avg={r.avg_latency_ms:6.2f}ms p95={r.p95_latency_ms:6.2f}ms "
        f"db={r.db_total:5} hit={r.cache_hit_rate_pct:5.1f}% "
        f"errors={r.errors}"
    )
    if r.strategy == "write_back":
        print(
            f"    write-back: flushes={r.write_back_flushes} "
            f"flushed_items={r.write_back_flushed_items}"
        )


def save_results(results: List[RunResult], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "benchmark_results.csv"
    md_path = out_dir / "benchmark_results.md"

    fields = [
        "strategy",
        "profile",
        "duration_s",
        "target_rps",
        "total_requests",
        "read_requests",
        "write_requests",
        "throughput_rps",
        "avg_latency_ms",
        "p95_latency_ms",
        "db_reads",
        "db_writes",
        "db_total",
        "cache_hit_rate_pct",
        "write_back_flushes",
        "write_back_flushed_items",
        "errors",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in results:
            writer.writerow({k: getattr(r, k) for k in fields})

    lines = [
        "# Результаты бенчмарка кеширования",
        "",
        "| Стратегия | Профиль | Throughput (req/s) | Avg latency (ms) | P95 (ms) | DB ops | Hit rate % |",
        "|-----------|---------|-------------------:|-----------------:|---------:|-------:|-----------:|",
    ]
    for r in results:
        lines.append(
            f"| {r.strategy} | {r.profile} | {r.throughput_rps} | "
            f"{r.avg_latency_ms} | {r.p95_latency_ms} | {r.db_total} | {r.cache_hit_rate_pct} |"
        )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path = out_dir / "benchmark_results.json"
    json_path.write_text(
        json.dumps([{k: getattr(r, k) for k in fields} for r in results], indent=2),
        encoding="utf-8",
    )
    print(f"\nSaved: {csv_path}, {md_path}, {json_path}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Cache strategy benchmark")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--rps", type=int, default=200)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--item-pool", type=int, default=500)
    parser.add_argument("--quick", action="store_true", help="Short run: 10s, 100 rps")
    parser.add_argument("--out-dir", type=str, default="results")
    parser.add_argument(
        "--strategies",
        type=str,
        default="cache_aside,write_through,write_back",
    )
    args = parser.parse_args()

    if args.quick:
        args.duration = 10
        args.rps = 100

    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    results: List[RunResult] = []

    print(
        f"Benchmark: duration={args.duration}s rps={args.rps} "
        f"workers={args.workers} pool={args.item_pool}"
    )
    print("=" * 90)

    for strategy in strategies:
        base_url = STRATEGIES[strategy]
        for profile, read_ratio in PROFILES.items():
            print(f"\n>>> {strategy} / {profile} (read={read_ratio:.0%})")
            r = await run_profile(
                strategy=strategy,
                base_url=base_url,
                profile=profile,
                read_ratio=read_ratio,
                duration_s=args.duration,
                target_rps=args.rps,
                item_pool=args.item_pool,
                workers=args.workers,
            )
            print_result(r)
            results.append(r)

    save_results(results, Path(args.out_dir))


if __name__ == "__main__":
    asyncio.run(main())
