"""
12-hour time conversion (#67), core/static/core/time12.js.

These run the real browser code under Node, so they're skipped where Node
isn't installed. GitHub's ubuntu-latest runner has it, so CI runs them.
"""

import json
import shutil
import subprocess
import unittest

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

NODE = shutil.which("node")


def run_time12(calls):
    """Evaluate [function, *args] calls against time12.js and return the results."""
    script = (
        "const t = require(process.argv[1]);"
        "const calls = JSON.parse(process.argv[2]);"
        "process.stdout.write(JSON.stringify(calls.map(([fn, ...args]) => t[fn](...args))));"
    )
    result = subprocess.run(
        [NODE, "-e", script, finders.find("core/time12.js"), json.dumps(calls)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    return json.loads(result.stdout)


@unittest.skipUnless(NODE, "Node is needed to run time12.js")
class To24Tests(SimpleTestCase):
    def check(self, cases):
        results = run_time12([["to24", *args] for args, _ in cases])
        for (args, expected), result in zip(cases, results):
            with self.subTest(args=args):
                self.assertEqual(result, expected)

    def test_8_pm_is_sent_as_20_00(self):
        self.check([(("8", "00", "PM"), "20:00")])

    def test_noon_midnight_and_padding(self):
        self.check([
            (("12", "00", "AM"), "00:00"),
            (("12", "30", "PM"), "12:30"),
            (("1", "5", "AM"), "01:05"),
            (("11", "59", "PM"), "23:59"),
            (("9", "", "AM"), "09:00"),  # an empty minute means :00
        ])

    def test_empty_means_no_filter(self):
        self.check([(("", "", "PM"), ""), (("  ", "", "AM"), "")])

    def test_invalid_input_is_null(self):
        self.check([
            (("13", "00", "PM"), None),
            (("0", "00", "AM"), None),
            (("8", "60", "PM"), None),
            (("8", "00", ""), None),
            (("x", "00", "PM"), None),
            (("", "30", "PM"), None),
        ])


@unittest.skipUnless(NODE, "Node is needed to run time12.js")
class From24Tests(SimpleTestCase):
    def test_round_trip_and_labels(self):
        results = run_time12([
            ["from24", "20:00"], ["from24", "00:15"], ["from24", "12:00:00"], ["from24", "25:00"],
            ["from24", ""], ["label", "20:05"], ["label", "09:30"],
        ])
        self.assertEqual(results, [
            {"hour": "8", "minute": "00", "period": "PM"},
            {"hour": "12", "minute": "15", "period": "AM"},
            {"hour": "12", "minute": "00", "period": "PM"},
            None,
            None,
            "8:05 PM",
            "9:30 AM",
        ])

    def test_every_24_hour_time_survives_a_round_trip(self):
        values = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 7, 30, 59)]
        parsed = run_time12([["from24", v] for v in values])
        back = run_time12([["to24", p["hour"], p["minute"], p["period"]] for p in parsed])
        self.assertEqual(back, values)
