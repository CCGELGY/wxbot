import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import prepare_hook


class HookPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = Path(self.tmp.name) / 'source.dll'
        self.output = Path(self.tmp.name) / 'output.dll'
        self.original = b'prefix0.0.0.0\0suffix'
        self.modified = b'prefix::1\0\0\0\0\0suffix'
        self.source.write_bytes(self.original)

    def tearDown(self):
        self.tmp.cleanup()

    def test_unknown_input_is_rejected_without_output(self):
        with self.assertRaises(ValueError):
            prepare_hook.prepare(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_preserved(self):
        self.output.write_bytes(b'keep')
        with self.assertRaises(ValueError):
            prepare_hook.prepare(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), b'keep')

    def test_same_path_never_overwrites_source(self):
        with self.assertRaises(ValueError):
            prepare_hook.prepare(self.source, self.source)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_result_digest_is_checked_before_writing(self):
        with patch.object(prepare_hook, 'UPSTREAM_SHA256', hashlib.sha256(self.original).hexdigest()):
            with self.assertRaises(ValueError):
                prepare_hook.prepare(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_only_bind_marker_changes_and_length_is_preserved(self):
        with patch.object(prepare_hook, 'UPSTREAM_SHA256', hashlib.sha256(self.original).hexdigest()), \
             patch.object(prepare_hook, 'LOOPBACK_SHA256', hashlib.sha256(self.modified).hexdigest()):
            prepare_hook.prepare(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), self.modified)
        self.assertEqual(len(self.modified), len(self.original))
        self.assertEqual(self.source.read_bytes(), self.original)


if __name__ == '__main__':
    unittest.main()
