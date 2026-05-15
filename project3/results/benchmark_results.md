# Результаты бенчмарка кеширования

| Стратегия | Профиль | Throughput (req/s) | Avg latency (ms) | P95 (ms) | DB ops | Hit rate % |
|-----------|---------|-------------------:|-----------------:|---------:|-------:|-----------:|
| cache_aside | read_heavy | 1228.5 | 6.5 | 18.53 | 13500 | 79.2 |
| cache_aside | balanced | 1204.03 | 6.64 | 18.04 | 26993 | 50.63 |
| cache_aside | write_heavy | 1214.93 | 6.58 | 16.68 | 34970 | 20.23 |
| write_through | read_heavy | 1201.47 | 6.65 | 19.0 | 7258 | 100.0 |
| write_through | balanced | 1160.27 | 6.89 | 18.24 | 17324 | 100.0 |
| write_through | write_heavy | 1122.1 | 7.13 | 17.79 | 26917 | 100.0 |
| write_back | read_heavy | 1210.53 | 6.6 | 19.92 | 1115 | 99.08 |
| write_back | balanced | 1151.37 | 6.94 | 20.42 | 900 | 100.0 |
| write_back | write_heavy | 1074.63 | 7.43 | 22.6 | 950 | 100.0 |
