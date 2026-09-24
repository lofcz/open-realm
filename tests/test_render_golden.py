"""Exercise harness failure propagation without retail assets or a GL display."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'tools/parity/render_golden.sh'


class GoldenHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.parity = self.root / 'tools/parity'
        self.parity.mkdir(parents=True)
        (self.parity / 'golden').mkdir()
        shutil.copy(SOURCE, self.parity / SOURCE.name)
        self.bin = self.root / 'build/bin'
        self.bin.mkdir(parents=True)
        self.tool('mdxtool', 'echo render-diagnostic >&2\nexit 1\n')
        self.tool('imgdiff', 'exit 0\n')
        self.data = self.root / 'data/Warcraft III'
        self.data.mkdir(parents=True)
        (self.data / 'test.mpq').touch()
        self.manifest('sample | test.mpq | Sample.mdx |\n')

    def tool(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\n' + body)
        path.chmod(0o755)

    def manifest(self, text):
        (self.parity / 'golden_manifest.txt').write_text(text)

    def run_harness(self, *args):
        return subprocess.run(['bash', str(self.parity / SOURCE.name), *args],
                              cwd=self.root, text=True, capture_output=True, timeout=10)

    def good_render(self):
        self.tool('mdxtool', 'while [ "$1" != -o ]; do shift; done\nprintf image > "$2"\n')

    def test_update_render_failure_is_failure(self):
        result = self.run_harness('--update')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.parity / 'golden/sample.png').exists())

    def test_failed_render_log_survives(self):
        self.run_harness()
        logs = list((self.root / 'build/parity').rglob('sample.log'))
        self.assertEqual(len(logs), 1)
        self.assertIn('render-diagnostic', logs[0].read_text())

    def test_empty_manifest_is_failure(self):
        self.manifest('# no test cases\n')
        self.assertNotEqual(self.run_harness().returncode, 0)

    def test_final_line_without_newline_runs(self):
        self.manifest('sample | test.mpq | Sample.mdx |')
        result = self.run_harness()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('RENDER-FAIL sample', result.stdout)

    def test_missing_output_is_failure(self):
        self.tool('mdxtool', 'exit 0\n')
        self.assertNotEqual(self.run_harness('--update').returncode, 0)

    def test_compare_failure_does_not_change_reference(self):
        self.good_render()
        ref = self.parity / 'golden/sample.png'
        ref.write_text('reference')
        self.tool('imgdiff', 'exit 1\n')
        self.assertNotEqual(self.run_harness().returncode, 0)
        self.assertEqual(ref.read_text(), 'reference')

    def test_repeat_mismatch_blocks_update(self):
        self.good_render()
        self.tool('imgdiff', 'exit 1\n')
        result = self.run_harness('--update', '--repeat')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('REPEAT-FAIL', result.stdout)
        self.assertFalse((self.parity / 'golden/sample.png').exists())

    def test_render_timeout_is_failure(self):
        self.tool('mdxtool', 'sleep 5\n')
        result = self.run_harness('--timeout', '0.1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('RENDER-FAIL', result.stdout)

    def test_archive_case_is_resolved(self):
        (self.data / 'test.mpq').rename(self.data / 'TEST.MPQ')
        self.good_render()
        self.assertEqual(self.run_harness('--update').returncode, 0)

    def test_ambiguous_archive_is_rejected(self):
        (self.data / 'test.mpq').rename(self.data / 'TEST.MPQ')
        (self.data / 'Test.mpq').touch()
        self.good_render()
        result = self.run_harness('--update')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ARCHIVE-FAIL', result.stdout)

    def test_successful_update(self):
        self.good_render()
        result = self.run_harness('--update')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.parity / 'golden/sample.png').read_text(), 'image')


if __name__ == '__main__':
    unittest.main()
