import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import state_store as store

class DurableStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=str(Path(self.tmp.name)/'seen.json')
        self.p=patch.object(store,'PATH',self.path);self.p.start();self.addCleanup(self.p.stop)
        self.content=json.dumps({'version':2,'feeds':{}}).encode()

    def test_restore_validates_then_writes(self):
        with patch.object(store,'request',return_value={'content':base64.b64encode(self.content).decode()}):store.main('restore')
        self.assertEqual(Path(self.path).read_bytes(),self.content)

    def test_corrupt_restore_preserves_local(self):
        Path(self.path).write_bytes(self.content)
        with patch.object(store,'request',return_value={'content':base64.b64encode(b'{}').decode()}):
            with self.assertRaises(ValueError):store.main('restore')
        self.assertEqual(Path(self.path).read_bytes(),self.content)

    def test_unchanged_state_does_not_commit(self):
        Path(self.path).write_bytes(self.content)
        with patch.object(store,'request',return_value={'content':base64.b64encode(self.content).decode()}) as req:store.main('save')
        self.assertEqual(req.call_count,1)
