from types import SimpleNamespace

from storage_metrics import StorageSampler, counter_rate


def test_counter_rate_requires_two_valid_samples_and_clamps_resets():
    assert counter_rate(None, 100, 1.0) is None
    assert counter_rate(100, 300, 2.0) == 100.0
    assert counter_rate(300, 100, 2.0) == 0.0


def test_disk_rates_calculate_throughput_iops_activity_and_latency():
    before = SimpleNamespace(read_bytes=1000, write_bytes=2000, read_count=10, write_count=20,
                             read_time=100, write_time=200, busy_time=500)
    after = SimpleNamespace(read_bytes=3000, write_bytes=6000, read_count=20, write_count=30,
                            read_time=300, write_time=500, busy_time=1500)
    result = StorageSampler._rates(before, after, 2.0)
    assert result["read_bytes_per_sec"] == 1000.0
    assert result["write_bytes_per_sec"] == 2000.0
    assert result["read_iops"] == 5.0
    assert result["write_iops"] == 5.0
    assert result["activity_percent"] == 50.0
    assert result["latency_ms"] == 20.0
