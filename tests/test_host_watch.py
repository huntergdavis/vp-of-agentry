import unittest

from host_watch import append_sample, load_level, tmp_level, GIB


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

    def test_load_requires_spaced_samples_and_recovers(self):
        history = []
        for at in (0, 60):
            history = append_sample(history, row(at, load15=14))
            self.assertEqual(load_level("ok", history), "ok")
        history = append_sample(history, row(120, load15=14))
        self.assertEqual(load_level("ok", history), "warning")
        for at in (180, 240):
            history = append_sample(history, row(at))
            self.assertEqual(load_level("warning", history), "warning")
        history = append_sample(history, row(300))
        self.assertEqual(load_level("warning", history), "ok")

    def test_critical_load_needs_two_spaced_samples(self):
        first = row(0, load1=21)
        history = append_sample([], first)
        self.assertEqual(load_level("ok", history), "ok")
        history = append_sample(history, row(5, load1=21))
        self.assertEqual(load_level("ok", history), "ok")
        history = append_sample(history, row(60, load1=21))
        self.assertEqual(load_level("ok", history), "critical")


if __name__ == "__main__":
    unittest.main()
