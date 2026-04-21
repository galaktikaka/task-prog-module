import argparse
import asyncio
import json
import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

import aio_pika
import redis.asyncio as redis


# Конфигурация одного прогона (один брокер + один размер + один rate).
@dataclass
class BenchmarkConfig:
    broker: str
    message_size: int
    rate: int
    duration_s: int
    producers: int
    consumers: int
    queue_name: str
    rabbit_url: str
    redis_url: str
    drain_timeout_s: int


@dataclass
class BenchmarkResult:
    broker: str
    message_size: int
    rate: int
    duration_s: int
    producers: int
    consumers: int
    sent: int
    send_errors: int
    received: int
    lost: int
    throughput_sent: float
    throughput_received: float
    avg_latency_ms: float
    p95_latency_ms: float
    max_latency_ms: float
    backlog_end: int
    degraded: bool


def parse_sizes(raw: str) -> List[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def parse_rates(raw: str) -> List[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


# Формирует сообщение фиксированного размера:
# служебные поля + payload из "x", чтобы сравнение брокеров было честным.
def build_payload(message_size: int, seq: int) -> bytes:
    base = {"seq": seq, "sent_ts": time.time_ns(), "payload": ""}
    header = json.dumps(base, separators=(",", ":")).encode("utf-8")
    overhead = len(header) + 2
    payload_len = max(0, message_size - overhead)
    base["payload"] = "x" * payload_len
    raw = json.dumps(base, separators=(",", ":")).encode("utf-8")
    return raw[:message_size]


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    idx = min(len(values) - 1, max(0, math.ceil((p / 100.0) * len(values)) - 1))
    return sorted(values)[idx]


class RabbitBroker:
    def __init__(self, url: str, queue_name: str):
        self.url = url
        self.queue_name = queue_name
        self.connection = None
        self.channel = None
        self.queue = None

    async def setup(self):
        # RabbitMQ иногда поднимается чуть позже контейнера.
        # Повторяем подключение несколько раз, чтобы избежать флаки-старта.
        last_error = None
        for attempt in range(10):
            try:
                self.connection = await aio_pika.connect_robust(self.url, timeout=5)
                self.channel = await self.connection.channel()
                await self.channel.set_qos(prefetch_count=1000)
                self.queue = await self.channel.declare_queue(self.queue_name, durable=False, auto_delete=True)
                await self.queue.purge()
                return
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(1 + attempt * 0.5)
        raise RuntimeError(f"RabbitMQ is not ready after retries: {last_error}")

    async def send(self, body: bytes):
        msg = aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT)
        await self.channel.default_exchange.publish(msg, routing_key=self.queue_name)

    async def consume_loop(self, stop_event: asyncio.Event, latencies_ms: List[float], counters: dict):
        # Читаем сообщения и считаем end-to-end latency по полю sent_ts.
        async with self.queue.iterator() as iterator:
            async for message in iterator:
                async with message.process(ignore_processed=True):
                    now_ns = time.time_ns()
                    try:
                        data = json.loads(message.body)
                        sent_ts = int(data["sent_ts"])
                        latencies_ms.append((now_ns - sent_ts) / 1_000_000)
                        counters["received"] += 1
                    except Exception:
                        counters["decode_errors"] += 1
                if stop_event.is_set():
                    break

    async def backlog(self) -> int:
        q = await self.channel.declare_queue(self.queue_name, durable=False, passive=True)
        return q.declaration_result.message_count

    async def close(self):
        if self.connection:
            await self.connection.close()


class RedisBroker:
    def __init__(self, url: str, queue_name: str):
        self.url = url
        self.queue_name = queue_name
        self.client = None

    async def setup(self):
        # Аналогично RabbitMQ: даем Redis время на готовность.
        self.client = redis.from_url(self.url, decode_responses=False)
        last_error = None
        for attempt in range(10):
            try:
                await self.client.ping()
                await self.client.delete(self.queue_name)
                return
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(0.5 + attempt * 0.3)
        raise RuntimeError(f"Redis is not ready after retries: {last_error}")

    async def send(self, body: bytes):
        await self.client.rpush(self.queue_name, body)

    async def consume_loop(self, stop_event: asyncio.Event, latencies_ms: List[float], counters: dict):
        # BLPOP с timeout, чтобы consumer мог завершиться по stop_event.
        while True:
            item = await self.client.blpop(self.queue_name, timeout=1)
            if item is not None:
                _, payload = item
                now_ns = time.time_ns()
                try:
                    data = json.loads(payload)
                    sent_ts = int(data["sent_ts"])
                    latencies_ms.append((now_ns - sent_ts) / 1_000_000)
                    counters["received"] += 1
                except Exception:
                    counters["decode_errors"] += 1
            if stop_event.is_set() and item is None:
                break

    async def backlog(self) -> int:
        return await self.client.llen(self.queue_name)

    async def close(self):
        if self.client:
            await self.client.aclose()


async def producer_loop(broker, cfg: BenchmarkConfig, producer_id: int, counters: dict):
    # Каждый producer отправляет равную долю целевого rate.
    target = cfg.rate / cfg.producers
    interval = 1.0 / max(target, 1)
    stop_at = time.perf_counter() + cfg.duration_s
    seq = producer_id * 10_000_000

    while time.perf_counter() < stop_at:
        started = time.perf_counter()
        body = build_payload(cfg.message_size, seq)
        try:
            await broker.send(body)
            counters["sent"] += 1
        except Exception:
            counters["send_errors"] += 1
        seq += 1
        elapsed = time.perf_counter() - started
        sleep_for = interval - elapsed
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)


async def run_case(cfg: BenchmarkConfig) -> BenchmarkResult:
    if cfg.broker == "rabbitmq":
        broker = RabbitBroker(cfg.rabbit_url, cfg.queue_name)
    elif cfg.broker == "redis":
        broker = RedisBroker(cfg.redis_url, cfg.queue_name)
    else:
        raise ValueError(f"Unknown broker: {cfg.broker}")

    await broker.setup()
    latencies_ms: List[float] = []
    counters = {"sent": 0, "send_errors": 0, "received": 0, "decode_errors": 0}
    stop_event = asyncio.Event()

    consumers = [
        asyncio.create_task(broker.consume_loop(stop_event, latencies_ms, counters))
        for _ in range(cfg.consumers)
    ]

    started = time.perf_counter()
    producers = [
        asyncio.create_task(producer_loop(broker, cfg, i, counters))
        for i in range(cfg.producers)
    ]
    await asyncio.gather(*producers)

    # Даем consumer время "дожать" хвост очереди после остановки producer.
    await asyncio.sleep(cfg.drain_timeout_s)
    stop_event.set()
    # Для RabbitMQ iterator может ждать следующее сообщение бесконечно,
    # поэтому явно отменяем consumer-задачи после drain-фазы.
    for task in consumers:
        task.cancel()
    await asyncio.gather(*consumers, return_exceptions=True)
    elapsed = time.perf_counter() - started

    backlog_end = await broker.backlog()
    await broker.close()

    sent = counters["sent"]
    received = counters["received"]
    lost = max(0, sent - received)
    avg_latency = statistics.mean(latencies_ms) if latencies_ms else 0.0
    p95 = percentile(latencies_ms, 95)
    max_lat = max(latencies_ms) if latencies_ms else 0.0
    throughput_sent = sent / elapsed if elapsed else 0.0
    throughput_received = received / elapsed if elapsed else 0.0

    degraded = (
        backlog_end > cfg.rate * 2
        or p95 > 200
        or counters["send_errors"] > 0
        or received < sent * 0.98
    )

    return BenchmarkResult(
        broker=cfg.broker,
        message_size=cfg.message_size,
        rate=cfg.rate,
        duration_s=cfg.duration_s,
        producers=cfg.producers,
        consumers=cfg.consumers,
        sent=sent,
        send_errors=counters["send_errors"],
        received=received,
        lost=lost,
        throughput_sent=throughput_sent,
        throughput_received=throughput_received,
        avg_latency_ms=avg_latency,
        p95_latency_ms=p95,
        max_latency_ms=max_lat,
        backlog_end=backlog_end,
        degraded=degraded,
    )


def to_csv_row(result: BenchmarkResult) -> str:
    fields = [
        result.broker,
        str(result.message_size),
        str(result.rate),
        str(result.duration_s),
        str(result.producers),
        str(result.consumers),
        str(result.sent),
        str(result.send_errors),
        str(result.received),
        str(result.lost),
        f"{result.throughput_sent:.2f}",
        f"{result.throughput_received:.2f}",
        f"{result.avg_latency_ms:.2f}",
        f"{result.p95_latency_ms:.2f}",
        f"{result.max_latency_ms:.2f}",
        str(result.backlog_end),
        str(result.degraded),
    ]
    return ",".join(fields)


def render_markdown(results: List[BenchmarkResult]) -> str:
    lines = [
        "# Результаты бенчмарка RabbitMQ vs Redis",
        "",
        "| broker | msg_size(B) | rate(msg/s) | sent | received | lost | recv msg/s | avg lat(ms) | p95(ms) | max(ms) | backlog | degraded |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.broker} | {r.message_size} | {r.rate} | {r.sent} | {r.received} | {r.lost} | "
            f"{r.throughput_received:.2f} | {r.avg_latency_ms:.2f} | {r.p95_latency_ms:.2f} | {r.max_latency_ms:.2f} | "
            f"{r.backlog_end} | {r.degraded} |"
        )
    return "\n".join(lines) + "\n"


async def main():
    parser = argparse.ArgumentParser(description="Broker benchmark: RabbitMQ vs Redis")
    parser.add_argument("--brokers", default="rabbitmq,redis")
    parser.add_argument("--sizes", default="128,1024,10240,102400")
    parser.add_argument("--rates", default="1000,5000,10000")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--producers", type=int, default=2)
    parser.add_argument("--consumers", type=int, default=2)
    parser.add_argument("--drain-timeout", type=int, default=5)
    parser.add_argument("--rabbit-url", default="amqp://guest:guest@localhost/")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--queue-prefix", default="bench.queue")
    parser.add_argument("--out-dir", default="results")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Быстрый прогон для проверки стенда (2 размера x 2 rates x 10s)",
    )
    args = parser.parse_args()

    brokers = [b.strip() for b in args.brokers.split(",") if b.strip()]
    sizes = parse_sizes(args.sizes)
    rates = parse_rates(args.rates)
    duration = args.duration

    # Быстрый режим нужен, чтобы проверить, что все работает, не ожидая полный цикл.
    if args.quick:
        sizes = [128, 1024]
        rates = [1000, 5000]
        duration = 10
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    header = (
        "broker,message_size,rate,duration_s,producers,consumers,sent,send_errors,received,lost,"
        "throughput_sent,throughput_received,avg_latency_ms,p95_latency_ms,max_latency_ms,backlog_end,degraded"
    )

    results: List[BenchmarkResult] = []
    csv_lines = [header]

    total_cases = len(brokers) * len(sizes) * len(rates)
    case_index = 0

    for broker in brokers:
        for size in sizes:
            for rate in rates:
                case_index += 1
                queue_name = f"{args.queue_prefix}.{broker}.{size}.{rate}"
                cfg = BenchmarkConfig(
                    broker=broker,
                    message_size=size,
                    rate=rate,
                    duration_s=duration,
                    producers=args.producers,
                    consumers=args.consumers,
                    queue_name=queue_name,
                    rabbit_url=args.rabbit_url,
                    redis_url=args.redis_url,
                    drain_timeout_s=args.drain_timeout,
                )
                # Явный прогресс, чтобы было видно, что скрипт работает.
                print(
                    f"[{case_index}/{total_cases}] Running: broker={broker} "
                    f"size={size}B rate={rate}msg/s duration={duration}s"
                )
                result = await run_case(cfg)
                results.append(result)
                csv_lines.append(to_csv_row(result))

    csv_path = out_dir / "benchmark_results.csv"
    md_path = out_dir / "benchmark_results.md"
    csv_path.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(results), encoding="utf-8")
    print(f"Saved: {csv_path}")
    print(f"Saved: {md_path}")


if __name__ == "__main__":
    asyncio.run(main())
