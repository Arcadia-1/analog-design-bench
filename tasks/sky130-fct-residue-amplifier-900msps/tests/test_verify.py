#!/usr/bin/env python3
"""Focused contract regressions for the FCT sampled-data verifier."""

import math
import unittest
from unittest import mock

import verify


def sampled_values(
    sample_count=32,
    tone_bin=5,
    output_peak=60e-3,
    nyquist_peak=0.0,
    power_w=4e-3,
    early_scale=1.0,
):
    values = {"power_w": power_w}
    for index in range(sample_count):
        phase = 2 * math.pi * tone_bin * index / sample_count
        differential = output_peak * math.sin(phase) + nyquist_peak * ((-1) ** index)
        outp = 0.9 + differential / 2
        outn = 0.9 - differential / 2
        values[f"outp_{index:03d}"] = outp
        values[f"outn_{index:03d}"] = outn
        values[f"outp_early_{index:03d}"] = 0.9 + early_scale * differential / 2
        values[f"outn_early_{index:03d}"] = 0.9 - early_scale * differential / 2
    return values


class FctVerifierRegression(unittest.TestCase):
    def metric_row(self, **updates):
        row = {
            "corner": "tt",
            "gain_vv": 6.0,
            "sfdr_db": 70.0,
            "cm_mean_v": 0.9,
            "output_min_v": 0.8,
            "output_max_v": 1.0,
            "hold_movement_ratio": 0.0,
            "power_w": 4e-3,
        }
        row.update(updates)
        return row

    def test_analyze_rejects_missing_and_nonfinite_measurements(self):
        values = sampled_values()
        self.assertIsNotNone(verify.analyze(values, 32, 5, 10e-3))
        for name in ("outp_000", "outp_early_000"):
            for replacement in (None, math.nan, math.inf, -math.inf):
                with self.subTest(name=name, replacement=replacement):
                    bad = values.copy()
                    if replacement is None:
                        del bad[name]
                    else:
                        bad[name] = replacement
                    self.assertIsNone(verify.analyze(bad, 32, 5, 10e-3))

    def test_hold_movement_is_normalized_differential_rms(self):
        metrics = verify.analyze(sampled_values(early_scale=1.015), 32, 5, 10e-3)
        self.assertIsNotNone(metrics)
        self.assertAlmostEqual(
            metrics["hold_movement_ratio"], verify.HOLD_MOVEMENT_MAX_RATIO, places=12
        )

    def test_analyze_rejects_nonfinite_total_power(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                self.assertIsNone(
                    verify.analyze(sampled_values(power_w=value), 32, 5, 10e-3)
                )

    def test_nyquist_bin_is_included_in_sfdr(self):
        metrics = verify.analyze(
            sampled_values(nyquist_peak=3e-3), 32, 5, 10e-3
        )
        self.assertIsNotNone(metrics)
        self.assertAlmostEqual(metrics["sfdr_db"], 20.0, places=6)

    def test_zero_fundamental_returns_finite_failing_metrics(self):
        metrics = verify.analyze(sampled_values(output_peak=0.0), 32, 5, 10e-3)
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics["gain_vv"], 0.0)
        self.assertTrue(math.isfinite(metrics["sfdr_db"]))

    def test_exact_metric_boundaries_pass_and_power_outside_range_fails(self):
        results = {}
        verify.add_metric_checks(
            results,
            [self.metric_row(
                gain_vv=5.5,
                sfdr_db=60.0,
                cm_mean_v=0.3,
                output_min_v=0.2,
                output_max_v=1.6,
                hold_movement_ratio=verify.HOLD_MOVEMENT_MAX_RATIO,
                power_w=0.0,
            )],
            "10mv",
        )
        self.assertTrue(all(check[1] for check in results.values()))
        for bad_power in (-1e-12, 5.000001e-3):
            with self.subTest(bad_power=bad_power):
                bad = {}
                verify.add_metric_checks(bad, [self.metric_row(power_w=bad_power)], "10mv")
                self.assertFalse(bad["power_pvt_10mv"][1])

    def test_each_electrical_limit_rejects_a_violation(self):
        violations = (
            ("sampled_gain_pvt_10mv", {"gain_vv": 5.499999}),
            ("sampled_gain_pvt_10mv", {"gain_vv": 6.500001}),
            ("sfdr_pvt_10mv", {"sfdr_db": 59.999999}),
            ("output_common_mode_pvt_10mv", {"cm_mean_v": 0.299999}),
            ("output_common_mode_pvt_10mv", {"cm_mean_v": 1.200001}),
            ("output_headroom_pvt_10mv", {"output_min_v": 0.199999}),
            ("output_headroom_pvt_10mv", {"output_max_v": 1.600001}),
            (
                "hold_transition_movement_pvt_10mv",
                {"hold_movement_ratio": verify.HOLD_MOVEMENT_MAX_RATIO + 1e-9},
            ),
            ("power_pvt_10mv", {"power_w": -1e-12}),
            ("power_pvt_10mv", {"power_w": 5.000001e-3}),
        )
        for check_name, update in violations:
            with self.subTest(check_name=check_name, update=update):
                results = {}
                verify.add_metric_checks(results, [self.metric_row(**update)], "10mv")
                self.assertFalse(results[check_name][1])

    def test_complete_requires_each_expected_corner_once(self):
        rows = [self.metric_row(corner=corner) for corner in verify.POINTS]
        self.assertTrue(verify.complete(rows, verify.POINTS))
        self.assertFalse(verify.complete(rows[:-1], verify.POINTS))
        duplicate = rows[:-1] + [self.metric_row(corner="tt")]
        self.assertFalse(verify.complete(duplicate, verify.POINTS))

    def test_bad_nominal_gate_does_not_launch_remaining_cases(self):
        nominal = [
            ("10mv", self.metric_row(gain_vv=1.0)),
            ("20mv", self.metric_row()),
        ]
        with mock.patch.object(verify, "run_cases", return_value=nominal) as run_cases, mock.patch.object(
            verify, "write_results"
        ):
            verify.main()
        run_cases.assert_called_once()
        self.assertEqual(run_cases.call_args.args[0], verify.NOMINAL_CASES)

    def test_passing_nominal_gate_launches_only_the_remaining_eight(self):
        nominal = [("10mv", self.metric_row()), ("20mv", self.metric_row())]
        remaining = []
        for amplitude in ("10mv", "20mv"):
            for corner in verify.POINTS[1:]:
                remaining.append((amplitude, self.metric_row(corner=corner)))
        with mock.patch.object(
            verify, "run_cases", side_effect=(nominal, remaining)
        ) as run_cases, mock.patch.object(verify, "write_results"):
            verify.main()
        self.assertEqual(run_cases.call_count, 2)
        self.assertEqual(run_cases.call_args_list[0].args[0], verify.NOMINAL_CASES)
        self.assertEqual(run_cases.call_args_list[1].args[0], verify.REMAINING_CASES)
        self.assertEqual(len(verify.REMAINING_CASES), 8)

if __name__ == "__main__":
    unittest.main()
