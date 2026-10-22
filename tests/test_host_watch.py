import unittest

from host_watch import append_sample, levels_for, tmp_level, GIB


def row(at, *, tmp_used=0.1, free=7, inodes=0.01, load1=2, load5=2,
        load15=2, psi=1):
    return {
        "at": at,
        "tmp_used_fraction": tmp_used,
        "tmp_free_bytes": free * GIB,
        "tmp_inode_used_fraction": inodes,
        "cpus": 8,
        "load1": load1,
        "load5": load5,
        "load15": load15,
        "cpu_psi_some_avg60": psi,
    }


class HostWatchThresholdTests(unittest.TestCase):
    def test_tmp_space_and_inode_thresholds(self):
        self.assertEqual(tmp_level(row(0)), "ok")
        self.assertEqual(tmp_level(row(0, tmp_used=0.61)), "warning")
        self.assertEqual(tmp_level(row(0, free=0.7)), "critical")
        self.assertEqual(tmp_level(row(0, inodes=0.91)), "critical")

    def test_load_is_reported_but_never_pages(self):
        # One owner for load: the dunkingsheep watchdog. host_watch reports the
        # numbers only - no level, so there is no second band.
        levels, report = levels_for(row(0, load1=21, tmp_used=0.1), {"tmp": "ok"})
        self.assertEqual({"tmp": "ok"}, levels)   # load never enters alert levels
        self.assertEqual(21, report["load1"])
        self.assertNotIn("level", report)

    def test_tmp_still_pages(self):
        levels, _ = levels_for(row(0, tmp_used=0.61), {"tmp": "ok"})
        self.assertEqual("warning", levels["tmp"])


if __name__ == "__main__":
    unittest.main()
