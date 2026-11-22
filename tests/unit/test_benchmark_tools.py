"""Herramientas del banco de pruebas: métricas, escenarios y lectura de estadísticas de Siddhi."""

from __future__ import annotations

import pytest

from scripts.benchmark.metrics import Confusion, confusion_by_type, percentile, summarize
from scripts.benchmark.scenarios import catalog, expand
from scripts.benchmark.siddhi_stats import parse, rows


def test_percentile_matches_linear_interpolation() -> None:
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert percentile(values, 50) == 5.5
    assert percentile(values, 95) == pytest.approx(9.55)
    assert percentile([], 95) is None
    assert percentile([7], 99) == 7


def test_summarize_gives_mean_median_and_tail() -> None:
    stats = summarize([10, 20, 30, 40])
    assert stats["count"] == 4 and stats["mean"] == 25 and stats["median"] == 25
    assert stats["min"] == 10 and stats["max"] == 40
    assert summarize([])["mean"] is None


def test_confusion_counts_tp_fp_fn_per_event_type() -> None:
    matrix = confusion_by_type({"ROUTE_DEVIATION": 2}, {"ROUTE_DEVIATION": 1, "DESTINATION_ARRIVAL": 1})
    assert (matrix["ROUTE_DEVIATION"].tp, matrix["ROUTE_DEVIATION"].fn) == (1, 1)
    assert matrix["DESTINATION_ARRIVAL"].fp == 1  # detectado sin esperarse
    total = Confusion()
    for value in matrix.values():
        total.add(value)
    assert total.precision == 0.5 and total.recall == 0.5 and total.f1 == 0.5
    assert Confusion().precision is None and Confusion().f1 is None


def test_every_rule_has_positive_negative_and_boundary_scenarios() -> None:
    scenarios = catalog()
    ids = [s.id for s in scenarios]
    assert len(ids) == len(set(ids))
    for rule in ("ROUTE_DEVIATION", "PROLONGED_STOP", "DESTINATION_ARRIVAL", "CONNECTION_LOSS", "EMERGENCY"):
        categories = {s.category for s in scenarios if s.rule == rule}
        assert "positive" in categories and ({"negative", "boundary"} & categories), rule


def test_expanded_scenario_keeps_inputs_config_and_expected_result() -> None:
    scenario = next(s for s in catalog() if s.id == "ARR-B1")
    spec = expand(scenario, "trip-1", 1_000)
    readings = [step["reading"] for step in spec["steps"]]
    assert [r["sequence"] for r in readings] == [1, 2]
    assert readings[1]["event_time_ms"] - readings[0]["event_time_ms"] == 1500  # justo la confirmación
    assert spec["config"]["arrival_confirmation_ms"] == 1500
    assert spec["expected"] == {"DESTINATION_ARRIVAL": 1}


LOG = """
[2026-11-17 16:33:00,001]  INFO {org.wso2.carbon.metrics} - metrics
io.siddhi.SiddhiApps.CargoMonitoring.Siddhi.Queries.deviation-detect.latency
             count = 200
         mean rate = 3.12 calls/second
               max = 6.80 milliseconds
              mean = 0.08 milliseconds
            median = 0.02 milliseconds
              95% <= 0.06 milliseconds
              99% <= 0.30 milliseconds
            99.9% <= 6.80 milliseconds

io.siddhi.SiddhiApps.CargoMonitoring.Siddhi.Streams.EnrichedTelemetryStream.throughput
             count = 500
         mean rate = 12.50 events/second

io.siddhi.SiddhiApps.Otra.Siddhi.Queries.q.latency
             count = 9
"""


def test_native_siddhi_statistics_are_parsed_from_the_console_reporter() -> None:
    metrics = parse(LOG)
    assert set(metrics) == {"Queries.deviation-detect.latency", "Streams.EnrichedTelemetryStream.throughput"}
    by_component = {(r["component"], r["kind"]): r for r in rows(metrics)}
    latency = by_component[("deviation-detect", "latency")]
    assert latency["count"] == 200 and latency["p95_ms"] == 0.06 and latency["p999_ms"] == 6.8
    assert latency["mean_ms"] == 0.08 and latency["max_ms"] == 6.8
    assert by_component[("EnrichedTelemetryStream", "throughput")]["mean_rate_per_s"] == 12.5
