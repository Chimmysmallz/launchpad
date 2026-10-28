"""End-to-end smoke test: starts LaunchPad, deploys an app, checks the links.

Uses only the Python standard library. Run with:  python -m unittest -v
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = 18100
BASE = f"http://127.0.0.1:{DASH}"
TOKEN = {"value": ""}


def call(method, url, data=None, headers=None, token=True):
    headers = dict(headers or {})
    if token and method != "GET" and url.startswith(BASE):
        headers.setdefault("X-LaunchPad-Token", TOKEN["value"])
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def api(method, path, obj=None):
    body = json.dumps(obj or {}).encode() if method != "GET" else None
    status, _, raw = call(method, BASE + path, body)
    return status, json.loads(raw)


class LaunchPadSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = tempfile.mkdtemp(prefix="launchpad-data-")
        env = dict(os.environ, LAUNCHPAD_PORT=str(DASH), LAUNCHPAD_DATA=cls.data)
        cls.proc = subprocess.Popen([sys.executable, str(ROOT / "launchpad.py"), "--no-browser"],
                                    cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                page = call("GET", BASE + "/")[2].decode()
                TOKEN["value"] = page.split('name="lp-token" content="')[1].split('"')[0]
                return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError("LaunchPad did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)
        shutil.rmtree(cls.data, ignore_errors=True)

    def deploy_files(self, files, name=None, slug=None):
        _, job = api("POST", "/api/deploy/start", {"name": name, "slug": slug})
        base = f'/api/deploy/{job["slug"]}/{job["deploy"]}'
        for path, content in files.items():
            status, _, _ = call("PUT", f"{BASE}{base}/file?path={path}", content)
            self.assertEqual(status, 200)
        status, body = api("POST", base + "/finish")
        self.assertEqual(status, 200, body)
        return body["site"], job["deploy"]

    def test_dashboard_loads(self):
        status, _, body = call("GET", BASE + "/")
        self.assertEqual(status, 200)
        self.assertIn(b"LaunchPad", body)

    def test_deploy_serve_and_rollback(self):
        site, first = self.deploy_files({
            "myapp/dist/index.html": b"<html><body><h1>v1</h1></body></html>",
            "myapp/dist/css/app.css": b"h1{color:red}",
            "myapp/dist/about.html": b"<p>about</p>",
            "myapp/node_modules/junk.js": b"skip me",
        }, name="Test App")
        app = f'http://127.0.0.1:{site["port"]}'
        status, _, body = call("GET", app + "/")
        self.assertEqual(status, 200)
        self.assertIn(b"v1", body)
        self.assertIn(b"LaunchPad live reload", body)
        status, headers, _ = call("GET", app + "/css/app.css")
        self.assertTrue(headers["Content-Type"].startswith("text/css"))
        self.assertIn(b"about", call("GET", app + "/about")[2])
        self.assertEqual(call("GET", app + "/nope.js")[0], 404)
        self.assertEqual(call("GET", app + "/node_modules/junk.js")[0], 404)
        status, headers, body = call("GET", app + "/css/app.css", headers={"Range": "bytes=0-1"})
        self.assertEqual((status, body), (206, b"h1"))

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("wrapper/index.html", "<body>v2</body>")
        _, job = api("POST", "/api/deploy/start", {"slug": site["slug"]})
        base = f'/api/deploy/{job["slug"]}/{job["deploy"]}'
        self.assertEqual(call("PUT", BASE + base + "/zip", buf.getvalue())[0], 200)
        self.assertEqual(api("POST", base + "/finish")[0], 200)
        self.assertIn(b"v2", call("GET", app + "/")[2])

        api("POST", f'/api/sites/{site["slug"]}/rollback', {"deploy": first})
        self.assertIn(b"v1", call("GET", app + "/")[2])

        api("POST", f'/api/sites/{site["slug"]}/settings', {"spa": True})
        self.assertEqual(call("GET", app + "/some/route")[0], 200)

        status, _, raw = call("GET", f'{BASE}/api/sites/{site["slug"]}/download')
        self.assertIn("index.html", zipfile.ZipFile(io.BytesIO(raw)).namelist())

    def test_path_traversal_blocked(self):
        site, _ = self.deploy_files({"index.html": b"<body>safe</body>"}, name="Safe")
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", site["port"], timeout=10)
        conn.request("GET", "/%2e%2e/%2e%2e/%2e%2e/launchpad.py")
        self.assertEqual(conn.getresponse().status, 404)
        conn.close()

    def test_linked_folder_live_reload(self):
        folder = Path(tempfile.mkdtemp(prefix="launchpad-linked-"))
        try:
            (folder / "public").mkdir()
            (folder / "public" / "index.html").write_text("<body>one</body>")
            status, body = api("POST", "/api/link", {"path": str(folder), "name": "Linked"})
            self.assertEqual(status, 200, body)
            app = f'http://127.0.0.1:{body["site"]["port"]}'
            v1 = call("GET", app + "/__launchpad/version")[2]
            time.sleep(1.1)
            (folder / "public" / "index.html").write_text("<body>two</body>")
            self.assertNotEqual(v1, call("GET", app + "/__launchpad/version")[2])
            self.assertIn(b"two", call("GET", app + "/")[2])
            api("DELETE", f'/api/sites/{body["site"]["slug"]}')
            self.assertTrue((folder / "public" / "index.html").exists(), "linked folder must never be deleted")
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_bad_inputs(self):
        self.assertEqual(api("POST", "/api/link", {"path": "/definitely/not/here"})[0], 400)
        _, job = api("POST", "/api/deploy/start", {"name": "Empty"})
        self.assertEqual(api("POST", f'/api/deploy/{job["slug"]}/{job["deploy"]}/finish')[0], 400)


    # ------------------------------------------------------------ security
    def test_requests_without_token_are_refused(self):
        body = json.dumps({"path": str(ROOT)}).encode()
        status, _, _ = call("POST", BASE + "/api/link", body, {"Content-Type": "text/plain"}, token=False)
        self.assertEqual(status, 403)
        status, _, _ = call("POST", BASE + "/api/deploy/start", b"{}", {"X-LaunchPad-Token": "wrong"}, token=False)
        self.assertEqual(status, 403)

    def test_cross_site_origin_is_refused(self):
        status, _, _ = call("POST", BASE + "/api/deploy/start", b"{}", {"Origin": "http://evil.example"})
        self.assertEqual(status, 403)

    def test_dns_rebinding_host_is_refused(self):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", DASH, timeout=10)
        conn.request("GET", "/api/sites", headers={"Host": f"attacker.example:{DASH}"})
        self.assertEqual(conn.getresponse().status, 403)
        conn.close()

    def test_security_headers(self):
        _, headers, _ = call("GET", BASE + "/")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertNotIn("Python", headers.get("Server", ""))
        site, _ = self.deploy_files({"index.html": b"<body>h</body>", "a.js": b"1"}, name="Headers")
        _, h, _ = call("GET", f'http://127.0.0.1:{site["port"]}/a.js')
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")

    def test_zip_cannot_escape_its_folder(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../../escaped.txt", "x")
            z.writestr("/abs/escaped2.txt", "x")
            z.writestr("index.html", "<body>ok</body>")
        _, job = api("POST", "/api/deploy/start", {"name": "Zip Slip"})
        base = f'/api/deploy/{job["slug"]}/{job["deploy"]}'
        call("PUT", BASE + base + "/zip", buf.getvalue())
        status, body = api("POST", base + "/finish")
        self.assertEqual(status, 200)
        data = Path(self.data).resolve()
        for found in data.rglob("escaped*.txt"):
            self.assertTrue(str(found.resolve()).startswith(str(data)))
        self.assertFalse((data.parent / "escaped.txt").exists())
        self.assertEqual(body["site"]["deploys"][0]["files"], 3)  # all three land inside the deploy folder

    def test_linked_folder_limits(self):
        self.assertEqual(api("POST", "/api/link", {"path": str(Path.home())})[0], 400)
        self.assertEqual(api("POST", "/api/link", {"path": Path.cwd().anchor or "/"})[0], 400)
        folder = Path(tempfile.mkdtemp(prefix="launchpad-sub-"))
        try:
            (folder / "index.html").write_text("x")
            _, body = api("POST", "/api/link", {"path": str(folder)})
            slug = body["site"]["slug"]
            self.assertEqual(api("POST", f"/api/sites/{slug}/settings", {"publish_dir": "../.."})[0], 400)
            self.assertEqual(api("POST", f"/api/sites/{slug}/settings", {"port": "abc"})[0], 400)
            api("DELETE", f"/api/sites/{slug}")
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_names_are_cleaned(self):
        site, _ = self.deploy_files({"index.html": b"x"}, name="<img src=x onerror=alert(1)>" + "a" * 200)
        self.assertNotIn("<", site["name"])
        self.assertLessEqual(len(site["name"]), 80)


if __name__ == "__main__":
    unittest.main()
