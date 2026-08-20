from __future__ import annotations

from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from m0_artifact_mock import ArtifactIntegrityError, ArtifactPolicyError, ArtifactUnavailableOffline, Descriptor, fetch


class _Server(BaseHTTPRequestHandler):
    payload = b"m0 mock artifact"
    requests = 0
    corrupt = False
    oversize = False
    redirect = False
    def do_GET(self):
        type(self).requests += 1
        if type(self).redirect:
            self.send_response(302); self.send_header("Location", "http://127.0.0.1:1/"); self.end_headers(); return
        body = b"corrupt" if type(self).corrupt else type(self).payload
        if type(self).oversize: body += b"!"
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *_): pass


class ArtifactMockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Server)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
        cls.provider = {"mock": f"http://127.0.0.1:{cls.server.server_port}"}
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
    def descriptor(self):
        payload = _Server.payload
        return Descriptor("mock", sha256(payload).hexdigest(), len(payload), "mock", "authorized_private", "test-evidence")
    def test_download_cache_and_offline_hit(self):
        with TemporaryDirectory() as directory:
            path = fetch(self.descriptor(), cache_root=Path(directory), providers=self.provider)
            self.assertEqual(path.read_bytes(), _Server.payload)
            before = _Server.requests
            self.assertEqual(fetch(self.descriptor(), cache_root=Path(directory), providers=self.provider, offline=True), path)
            self.assertEqual(_Server.requests, before)
    def test_offline_miss_does_not_request(self):
        with TemporaryDirectory() as directory:
            before = _Server.requests
            with self.assertRaises(ArtifactUnavailableOffline): fetch(self.descriptor(), cache_root=Path(directory), providers=self.provider, offline=True)
            self.assertEqual(_Server.requests, before)
    def test_corrupt_download_and_policy_deny(self):
        with TemporaryDirectory() as directory:
            _Server.corrupt = True
            try:
                with self.assertRaises(ArtifactIntegrityError): fetch(self.descriptor(), cache_root=Path(directory), providers=self.provider)
                self.assertFalse(list(Path(directory).rglob("blob")))
                self.assertFalse(list(Path(directory).rglob("tmp*")))
            finally: _Server.corrupt = False
            denied = Descriptor("bad", self.descriptor().transport_sha256, len(_Server.payload), "mock", "blocked_unknown", "evidence")
            before = _Server.requests
            with self.assertRaises(ArtifactPolicyError): fetch(denied, cache_root=Path(directory), providers=self.provider)
            self.assertEqual(_Server.requests, before)
    def test_oversize_redirect_and_corrupt_offline_cache(self):
        with TemporaryDirectory() as directory:
            _Server.oversize = True
            try:
                with self.assertRaises(ArtifactIntegrityError): fetch(self.descriptor(), cache_root=Path(directory), providers=self.provider)
            finally: _Server.oversize = False
            _Server.redirect = True
            try:
                with self.assertRaises(ArtifactIntegrityError): fetch(self.descriptor(), cache_root=Path(directory), providers=self.provider)
            finally: _Server.redirect = False
            target = Path(directory) / "sha256" / self.descriptor().transport_sha256[:2] / self.descriptor().transport_sha256 / "blob"
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(b"bad")
            with self.assertRaises(ArtifactIntegrityError): fetch(self.descriptor(), cache_root=Path(directory), providers=self.provider, offline=True)


if __name__ == "__main__": unittest.main()
