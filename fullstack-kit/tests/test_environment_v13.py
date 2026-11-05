import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))


class ControlledEnvironment(unittest.TestCase):
    def setUp(self):
        self.assertTrue((SCRIPTS/'execution_environment.py').exists(), 'Controlled environment implementation required')
        from execution_environment import capture_environment, environment_matches
        self.capture = capture_environment
        self.matches = environment_matches
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root/'.fullstack').mkdir()
        (self.root/'package.json').write_text(json.dumps({'scripts':{'build':'node build.js'}}))
        (self.root/'build.js').write_text("if(process.env.REVIEW_BUILD_MODE!=='pass')process.exit(1);if(process.env.NODE_OPTIONS||process.env.UNKNOWN_INJECTION)process.exit(2);")
        self.command = ['npm','run','build']
        self.config(['REVIEW_BUILD_MODE'])

    def config(self, keys):
        (self.root/'.fullstack/checks.json').write_text(json.dumps({'P6':[{'check_id':'build','environment':{'keys':keys}}]}))

    def test_current_environment_change_invalidates_and_actual_npm_fails(self):
        from command_executor import execute
        with patch.dict(os.environ, {'REVIEW_BUILD_MODE':'pass','NODE_OPTIONS':'--invalid-option','UNKNOWN_INJECTION':'yes'}):
            env, manifest = self.capture(self.root,self.command,'build')
            self.assertEqual(0,execute(self.command,self.root,20,env=env)[1])
            self.assertNotIn('NODE_OPTIONS',env)
            os.environ['REVIEW_BUILD_MODE']='fail'
            self.assertFalse(self.matches(self.root,self.command,'build',manifest))
            env,_=self.capture(self.root,self.command,'build')
            self.assertEqual(1,execute(self.command,self.root,20,env=env)[1])

    def test_secret_name_value_and_loader_configuration_rejected(self):
        for name in ['API_TOKEN','NODE_OPTIONS','PYTHONPATH','PATH']:
            with self.subTest(name=name):
                self.config([name])
                with self.assertRaises(ValueError): self.capture(self.root,self.command,'build')
        self.config(['REVIEW_BUILD_MODE'])
        with patch.dict(os.environ,{'API_TOKEN':'1234','REVIEW_BUILD_MODE':'1234'}):
            with self.assertRaises(ValueError): self.capture(self.root,self.command,'build')

    def test_installed_dependency_changes_without_lockfile_change(self):
        dependency=self.root/'node_modules/demo/index.js'
        dependency.parent.mkdir(parents=True)
        dependency.write_text('module.exports=1')
        _,manifest=self.capture(self.root,self.command,'build')
        dependency.write_text('module.exports=2')
        self.assertFalse(self.matches(self.root,self.command,'build',manifest))

    def test_python_and_unlisted_low_entropy_secret_isolated(self):
        from command_executor import execute
        (self.root/'test_env.py').write_text("import os,unittest\nclass T(unittest.TestCase):\n def test_env(self):self.assertNotIn('TEST_TOKEN',os.environ)\n")
        cmd=[sys.executable,'-m','unittest','discover']
        with patch.dict(os.environ,{'TEST_TOKEN':'1234'}):
            env,manifest=self.capture(self.root,cmd,'build')
            self.assertNotIn('1234',json.dumps(manifest))
            self.assertNotIn('TEST_TOKEN',env)
            self.assertEqual(0,execute(cmd,self.root,20,env=env)[1])

    def test_unbound_python_executable_is_rejected(self):
        with tempfile.TemporaryDirectory() as tools:
            executable = Path(tools)/('python.exe' if os.name == 'nt' else 'python')
            shutil.copy2(sys.executable, executable)
            command = [str(executable), '-m', 'unittest']
            # A copied interpreter has no verified installation boundary.
            with self.assertRaises(ValueError):
                self.capture(self.root, command, 'build')

    def test_node_executable_bytes_change_invalidates_manifest(self):
        with tempfile.TemporaryDirectory() as tools:
            executable = Path(tools)/("node.exe" if os.name == "nt" else "node")
            shutil.copy2(shutil.which("node"), executable)
            command = [str(executable), str(self.root/"build.js")]
            _, manifest = self.capture(self.root, command, "build")
            with executable.open("ab") as stream:
                stream.write(b"changed binary identity")
            self.assertFalse(self.matches(self.root, command, "build", manifest))

    def test_external_venv_cannot_obtain_current_environment_evidence(self):
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            envroot = Path(folder)/"untrusted"
            subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(envroot)], check=True)
            python = envroot/("Scripts/python.exe" if os.name == "nt" else "bin/python")
            with self.assertRaises(ValueError):
                self.capture(self.root, [str(python), "-m", "unittest"], "build")
