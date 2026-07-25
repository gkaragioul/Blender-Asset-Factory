import unittest

from tests.fixtures import FixtureUnavailable, trenchgun_fbx


class FixtureHarnessTest(unittest.TestCase):
    def test_extracts_trenchgun_fixture(self):
        try:
            path = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, "trenchgun.fbx")
        self.assertGreater(path.stat().st_size, 1_000_000)

    def test_second_call_reuses_extraction(self):
        try:
            first = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))
        stamp = first.stat().st_mtime_ns
        self.assertEqual(trenchgun_fbx().stat().st_mtime_ns, stamp)


if __name__ == "__main__":
    unittest.main()
