import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))


class Artifacts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.image = Path(self.temp.name) / 'image'
        self.root.mkdir()
        (self.image / 'dist').mkdir(parents=True)
        (self.image / 'dist/app.js').write_bytes(b'compiled')
        self.outputs = [dict(path='dist', type='directory', max_bytes=100, max_files=10)]

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('artifacts'), 'artifact persistence missing')
        import artifacts
        return artifacts

    def test_publish_verify_mutation_and_missing(self):
        a = self.module()
        descriptor = a.publish(self.root, self.image, uuid.uuid4().hex, self.outputs)
        self.assertTrue(a.verify(self.root, descriptor))
        target = self.root / descriptor['location'] / 'files/dist/app.js'
        self.assertEqual(target.read_bytes(), b'compiled')
        target.write_bytes(b'tampered')
        self.assertFalse(a.verify(self.root, descriptor))
        target.unlink()
        self.assertFalse(a.verify(self.root, descriptor))

    def test_collision_and_independent_runs(self):
        a = self.module()
        run = uuid.uuid4().hex
        first = a.publish(self.root, self.image, run, self.outputs)
        with self.assertRaises((ValueError, FileExistsError)):
            a.publish(self.root, self.image, run, self.outputs)
        second = a.publish(self.root, self.image, uuid.uuid4().hex, self.outputs)
        self.assertNotEqual(first['location'], second['location'])
        self.assertTrue(a.verify(self.root, first))
        self.assertTrue(a.verify(self.root, second))

    def test_reject_invalid_paths_and_limits(self):
        a = self.module()
        for path in ('../dist', 'C:/dist', 'dist/app.js:extra', 'dist/CON', 'dist/../dist', 'dist\\app.js', 'dist.'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                a.publish(self.root, self.image, uuid.uuid4().hex, [dict(path=path, type='file', max_bytes=100, max_files=1)])
        for outputs in (self.outputs * 2, [dict(path='dist',type='directory',max_bytes=1,max_files=10)]):
            with self.assertRaises(ValueError):
                a.publish(self.root, self.image, uuid.uuid4().hex, outputs)

    def test_interrupted_publication_never_validates(self):
        a = self.module()
        run = uuid.uuid4().hex
        with patch.object(a, '_commit', side_effect=OSError('simulated interrupted commit')):
            with self.assertRaises(OSError):
                a.publish(self.root, self.image, run, self.outputs)
        self.assertFalse((self.root / '.fullstack/artifacts' / run).exists())
        self.assertTrue(a.verify(self.root, a.publish(self.root,self.image,run,self.outputs)))

    def test_killed_publisher_leaves_only_untrusted_staging(self):
        a = self.module()
        run = uuid.uuid4().hex
        marker = self.root.parent / "ready"
        script = (
            "import sys,json,time;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
            "import artifacts;"
            "artifacts._commit=lambda *a:(Path(sys.argv[6]).write_text('ready'),time.sleep(60));"
            "artifacts.publish(*sys.argv[2:5],json.loads(sys.argv[5]))")
        process = subprocess.Popen([sys.executable, "-B", "-c", script, str(SCRIPTS),
            str(self.root), str(self.image), run, json.dumps(self.outputs), str(marker)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        import time
        try:
            deadline = time.monotonic() + 15
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(marker.exists(), "publisher never reached pre-commit boundary")
            process.kill()
            process.communicate(timeout=10)
            self.assertFalse((self.root/".fullstack/artifacts"/run).exists())
            self.assertTrue(list((self.root/".fullstack/artifacts").glob(".staging-*")))
            recovered = a.publish(self.root, self.image, run, self.outputs)
            self.assertTrue(a.verify(self.root, recovered))
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)

    def test_two_processes_cannot_overwrite_same_run(self):
        a = self.module()
        run = uuid.uuid4().hex
        script = "import sys,json;sys.path.insert(0,sys.argv[1]);from artifacts import publish;publish(*sys.argv[2:5],json.loads(sys.argv[5]))"
        command = [sys.executable,'-B','-c',script,str(SCRIPTS),str(self.root),str(self.image),run,json.dumps(self.outputs)]
        processes = [subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        self.addCleanup(lambda: [p.kill() for p in processes if p.poll() is None])
        for process in processes:
            process.communicate(timeout=20)
        self.assertEqual(sorted(p.returncode for p in processes),[0,1])
        root = self.root/'.fullstack/artifacts'/run
        self.assertEqual((root/'files/dist/app.js').read_bytes(),b'compiled')
        self.assertEqual(len(list((self.root/'.fullstack/artifacts').glob('[0-9a-f]'*32))),1)

    def test_missing_outputs_and_hardlink_rejected(self):
        a = self.module()
        with self.assertRaises((OSError,ValueError)):
            a.publish(self.root,self.image,uuid.uuid4().hex,[dict(path='missing',type='file',max_bytes=100,max_files=1)])
        (self.image/'dist/alias.js').hardlink_to(self.image/'dist/app.js')
        with self.assertRaises(ValueError):
            a.publish(self.root,self.image,uuid.uuid4().hex,self.outputs)

    def test_unlisted_files_and_manifest_splicing(self):
        a = self.module()
        first = a.publish(self.root,self.image,uuid.uuid4().hex,self.outputs)
        second = a.publish(self.root,self.image,uuid.uuid4().hex,self.outputs)
        forged = dict(first,location=second['location'])
        self.assertFalse(a.verify(self.root, forged))
        (self.root / first['location'] / 'files/extra').write_text('extra')
        self.assertFalse(a.verify(self.root, first))

    @unittest.skipUnless(sys.platform == 'win32', 'Windows junction behavior')
    def test_directory_junction_rejected(self):
        a = self.module()
        subprocess.run(['cmd','/c','mklink','/J',str(self.image/'linked'),str(self.image/'dist')],check=True,capture_output=True)
        with self.assertRaises(ValueError):
            a.publish(self.root,self.image,uuid.uuid4().hex,[dict(path='linked',type='directory',max_bytes=100,max_files=10)])

    @unittest.skipUnless(sys.platform == 'win32', 'Windows junction behavior')
    def test_linked_destination_has_no_external_side_effects(self):
        a = self.module()
        outside = self.root.parent / "outside"
        outside.mkdir()
        subprocess.run(["cmd", "/c", "mklink", "/J", str(self.root/".fullstack"), str(outside)],
                       check=True, capture_output=True)
        with self.assertRaises(ValueError):
            a.publish(self.root, self.image, uuid.uuid4().hex, self.outputs)
        self.assertEqual([], list(outside.iterdir()))

    def test_final_delivery_files_match_retained_manifest(self):
        a = self.module()
        self.assertTrue(hasattr(a, "verify_delivery"), "final delivery verification missing")
        receipt = a.publish(self.root, self.image, uuid.uuid4().hex, self.outputs)
        self.assertTrue(a.verify_delivery(self.root, receipt, self.image))
        (self.image/"dist/app.js").write_text("different delivery")
        self.assertFalse(a.verify_delivery(self.root, receipt, self.image))
