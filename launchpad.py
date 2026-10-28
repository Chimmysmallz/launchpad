"""
LaunchPad - a local, Netlify-style test host for your web apps.

Drag a folder, a .zip or an .html file onto the dashboard and each app gets
its own address that works on this computer and on any phone on the same Wi-Fi.

Runs on plain Python 3.8+ with no required installs. If the optional
"qrcode" package is present, the dashboard also shows phone QR codes.
"""
import html
import io
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

try:
    import qrcode  # optional
except ImportError:
    qrcode = None

APP_DIR = Path(__file__).resolve().parent
DATA = Path(os.environ.get("LAUNCHPAD_DATA") or APP_DIR / "data")
SITES_DIR = DATA / "sites"
DB_FILE = DATA / "sites.json"
DASHBOARD = APP_DIR / "static" / "dashboard.html"
DASH_PORT = int(os.environ.get("LAUNCHPAD_PORT", "8100"))
FIRST_SITE_PORT = DASH_PORT + 1
KEEP_DEPLOYS = 10
PUBLISH_CANDIDATES = ["", "dist", "build", "public", "out", "site", "www", "docs"]
MAX_FILE_BYTES = 1024 ** 3          # 1 GB per uploaded file
MAX_DEPLOY_BYTES = 2 * 1024 ** 3    # 2 GB per deploy, after unzipping
MAX_DEPLOY_FILES = 20000
MAX_NAME = 80
TOKEN = secrets.token_urlsafe(32)   # new every run; only the dashboard page knows it
LAN_DASHBOARD = "--lan-dashboard" in sys.argv

SKIP_NAMES = {"node_modules", ".git", "__MACOSX", ".DS_Store", "Thumbs.db", "__pycache__", ".venv", "venv"}

# Windows sometimes maps .js to text/plain in the registry, which breaks modules.
for ext, typ in {".js": "application/javascript", ".mjs": "application/javascript", ".css": "text/css",
                 ".svg": "image/svg+xml", ".json": "application/json", ".wasm": "application/wasm",
                 ".webmanifest": "application/manifest+json", ".webp": "image/webp", ".mp4": "video/mp4",
                 ".woff2": "font/woff2", ".woff": "font/woff", ".html": "text/html", ".htm": "text/html"}.items():
    mimetypes.add_type(typ, ext)

lock = threading.RLock()
servers = {}   # slug -> ThreadingHTTPServer
DB = {"sites": {}}

DASH_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; script-src 'self' 'unsafe-inline'; "
                                "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
                                "frame-ancestors 'none'; base-uri 'none'; form-action 'none'; object-src 'none'"),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
APP_HEADERS = {"X-Content-Type-Options": "nosniff", "Access-Control-Allow-Origin": "*"}

LIVE_RELOAD = (b"<script>/* LaunchPad live reload */(function(){var v=null;function c(){"
               b"fetch('/__launchpad/version',{cache:'no-store'}).then(function(r){return r.json()})"
               b".then(function(d){if(v===null){v=d.v}else if(d.v!==v){location.reload()}}).catch(function(){})}"
               b"c();setInterval(c,1000)})();</script>")


# ================================================================ storage
def load_db():
    global DB
    SITES_DIR.mkdir(parents=True, exist_ok=True)
    if DB_FILE.exists():
        try:
            DB = json.loads(DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            shutil.copy(DB_FILE, DB_FILE.with_suffix(".broken.json"))
            DB = {"sites": {}}
    DB.setdefault("sites", {})


def save_db():
    tmp = DB_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(DB, indent=2), encoding="utf-8")
    os.replace(tmp, DB_FILE)


# ================================================================ network
def lan_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    ips = [i for i in ips if not i.startswith("127.")]
    return ips or ["127.0.0.1"]


def port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def next_port():
    used = {s["port"] for s in DB["sites"].values()} | {DASH_PORT}
    p = FIRST_SITE_PORT
    while p in used or not port_free(p):
        p += 1
    return p


# ================================================================ helpers
def slugify(text):
    return (re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40]) or "app"


def clean_name(name):
    name = re.sub(r"[\x00-\x1f<>]", "", str(name or "")).strip()
    return name[:MAX_NAME]


def safe_subdir(value):
    """A sub-folder such as 'dist' or 'site/public'. Never '..' or an absolute path."""
    raw = str(value or "").strip().replace("\\", "/").strip("/")
    if not raw:
        return ""
    parts = raw.split("/")
    if any(p in ("", ".", "..") or ":" in p for p in parts):
        raise ValueError("The sub-folder must be inside the linked folder, for example dist.")
    return "/".join(parts)


def too_broad(p):
    """Refuse to share a whole drive or the home folder over Wi-Fi."""
    p = p.resolve()
    anchor = Path(p.anchor)
    return p == anchor or p == Path.home().resolve() or (p.parent == anchor and p.name.lower() in ("users", "home"))


def unique_slug(base):
    slug, n = base, 2
    while slug in DB["sites"]:
        slug, n = f"{base}-{n}", n + 1
    return slug


def clean_parts(rel):
    parts = [p for p in (rel or "").replace("\\", "/").split("/") if p not in ("", ".", "..")]
    if not parts or any(p in SKIP_NAMES for p in parts):
        return None
    return parts


def inside(child, root):
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def normalize_root(d):
    """If everything sits inside one wrapper folder, lift it up a level."""
    for _ in range(5):
        shutil.rmtree(d / "__MACOSX", ignore_errors=True)
        entries = [e for e in d.iterdir() if not e.name.startswith(".")]
        if len(entries) == 1 and entries[0].is_dir() and not (d / "index.html").exists():
            tmp = d.with_name(d.name + ".lift")
            shutil.move(str(entries[0]), str(tmp))
            shutil.rmtree(d)
            tmp.rename(d)
        else:
            return


def detect_publish_dir(root):
    for c in PUBLISH_CANDIDATES:
        if (root / c / "index.html").is_file():
            return c
    return ""


def folder_stats(root):
    count = size = 0
    for p in root.rglob("*"):
        if p.is_file():
            count += 1
            size += p.stat().st_size
    return count, size


def site_root(slug):
    site = DB["sites"].get(slug)
    if not site:
        return None
    if site["type"] == "linked":
        return Path(site["path"]) / site.get("publish_dir", "")
    dep = next((d for d in site.get("deploys", []) if d["id"] == site.get("current")), None)
    if not dep:
        return None
    return SITES_DIR / slug / "deploys" / dep["id"] / dep.get("publish_dir", "")


def site_version(slug):
    site = DB["sites"].get(slug)
    if not site:
        return "gone"
    stamp = f'{site.get("spa")}-{site.get("livereload")}-{site.get("publish_dir", "")}'
    if site["type"] != "linked":
        return f'{site.get("current")}-{stamp}'
    root, latest, seen = site_root(slug), 0.0, 0
    if root and root.exists():
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [n for n in dirnames if n not in SKIP_NAMES]
            for f in filenames:
                try:
                    latest = max(latest, os.path.getmtime(os.path.join(dirpath, f)))
                except OSError:
                    pass
                seen += 1
            if seen > 5000:
                break
    return f"{latest:.3f}-{stamp}"


def public_site(slug):
    s = dict(DB["sites"][slug])
    s.update(slug=slug, running=slug in servers, local_url=f'http://localhost:{s["port"]}/')
    return s


# ================================================================ base handler
class Base(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LaunchPad"
    sys_version = ""
    EXTRA = {}

    def log_message(self, *args):  # keep the console quiet
        pass

    def send(self, status, body=b"", ctype="text/html; charset=utf-8", headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in {**self.EXTRA, **(headers or {})}.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, data, status=200):
        self.send(status, json.dumps(data), "application/json")

    def body_json(self):
        n = min(int(self.headers.get("Content-Length") or 0), 1 << 20)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def body_to_file(self, fh, limit=MAX_FILE_BYTES):
        remaining = int(self.headers.get("Content-Length") or 0)
        if remaining > limit:
            self.close_connection = True
            raise ValueError("That file is too large for LaunchPad (limit 1 GB).")
        while remaining > 0:
            chunk = self.rfile.read(min(1 << 20, remaining))
            if not chunk:
                break
            fh.write(chunk)
            remaining -= len(chunk)


# ================================================================ app servers
def resolve_file(root, req_path, spa):
    clean = req_path.strip("/")
    p = (root / clean) if clean else root
    if not inside(p, root):
        return "missing", None
    if p.is_dir():
        if clean and not req_path.endswith("/"):
            return "redirect", "/" + clean + "/"
        if (p / "index.html").is_file():
            return "file", p / "index.html"
        htmls = sorted(p.glob("*.html"))
        if len(htmls) == 1:
            return "file", htmls[0]
        return "listing", p
    if p.is_file():
        return "file", p
    if not p.suffix and p.with_suffix(".html").is_file():   # /about -> about.html
        return "file", p.with_suffix(".html")
    if spa and not Path(clean).suffix and (root / "index.html").is_file():
        return "file", root / "index.html"
    return "missing", None


def listing_page(p, root):
    rel = p.relative_to(root).as_posix()
    rel = "" if rel == "." else rel
    items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    rows = "".join(f'<li><a href="{html.escape(x.name)}{"/" if x.is_dir() else ""}">{html.escape(x.name)}{"/" if x.is_dir() else ""}</a></li>'
                   for x in items if not x.name.startswith("."))
    return (f"<!doctype html><meta charset=utf-8><title>Files</title><body style='font-family:Segoe UI,Arial;"
            f"padding:24px'><h2>/{html.escape(rel)}</h2><p>There is no index.html here, so LaunchPad is listing the files.</p>"
            f"<ul>{rows}</ul></body>")


def make_site_handler(slug):
    class SiteHandler(Base):
        EXTRA = APP_HEADERS
        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == "/__launchpad/version":
                return self.json({"v": site_version(slug)})
            site, root = DB["sites"].get(slug), site_root(slug)
            if not site or not root or not root.exists():
                return self.send(404, "<h2>This app has no live version yet.</h2>")
            kind, val = resolve_file(root, path, site.get("spa", False))
            if kind == "redirect":
                return self.send(301, b"", headers={"Location": val})
            if kind == "listing":
                return self.send(200, listing_page(val, root))
            status = 200
            if kind == "missing":
                val = root / "404.html"
                if not val.is_file():
                    return self.send(404, f"<h2>404: {html.escape(path)} was not found in this app.</h2>")
                status = 404
            ctype = mimetypes.guess_type(val.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            if val.suffix.lower() in (".html", ".htm"):
                body = val.read_bytes()
                if site.get("livereload", True):
                    i = body.lower().rfind(b"</body>")
                    body = body[:i] + LIVE_RELOAD + body[i:] if i != -1 else body + LIVE_RELOAD
                return self.send(status, body, ctype)
            self.send_file(val, ctype, status)

        do_HEAD = do_GET

        def send_file(self, p, ctype, status):
            size = p.stat().st_size
            start, end = 0, size - 1
            rng = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
            if rng and status == 200 and size:
                a, b = rng.groups()
                if a:
                    start, end = int(a), min(int(b), size - 1) if b else size - 1
                elif b:
                    start = max(0, size - int(b))
                if start > end:
                    return self.send(416, b"", headers={"Content-Range": f"bytes */{size}"})
                status = 206
            length = end - start + 1 if size else 0
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            for k, v in APP_HEADERS.items():
                self.send_header(k, v)
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if self.command == "HEAD" or not length:
                return
            with open(p, "rb") as f:
                f.seek(start)
                left = length
                try:
                    while left > 0:
                        chunk = f.read(min(1 << 16, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
                except (ConnectionResetError, BrokenPipeError):
                    pass

    return SiteHandler


def start_site(slug):
    if slug in servers:
        return True
    site = DB["sites"][slug]
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", site["port"]), make_site_handler(slug))
    except OSError:
        site["error"] = f'Port {site["port"]} is busy. Pick another port in Settings.'
        return False
    srv.daemon_threads = True
    site.pop("error", None)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    servers[slug] = srv
    return True


def stop_site(slug):
    srv = servers.pop(slug, None)
    if srv:
        srv.shutdown()
        srv.server_close()


# ================================================================ deploy logic
def deploy_dir(slug, did):
    return SITES_DIR / slug / "deploys" / did


def begin_deploy(slug, name):
    with lock:
        if slug and slug in DB["sites"]:
            if DB["sites"][slug]["type"] == "linked":
                raise ValueError("Linked apps update by themselves. Save your files in the folder instead.")
        else:
            name = clean_name(name) or "My app"
            slug = unique_slug(slugify(name))
            DB["sites"][slug] = {"name": name, "type": "upload", "port": next_port(), "spa": False,
                                 "livereload": True, "deploys": [], "current": None,
                                 "created": time.time(), "updated": time.time()}
            start_site(slug)
            save_db()
    did = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    (deploy_dir(slug, did).with_name(did + ".partial")).mkdir(parents=True)
    return slug, did


def partial_dir(slug, did):
    if slug not in DB["sites"] or not re.fullmatch(r"[\w-]+", did or ""):
        raise ValueError("Unknown upload.")
    d = deploy_dir(slug, did).with_name(did + ".partial")
    if not d.is_dir():
        raise ValueError("Unknown upload.")
    return d


def extract_zip(fh, d):
    total = files = 0
    with zipfile.ZipFile(fh) as z:
        for m in z.infolist():
            parts = None if m.is_dir() else clean_parts(m.filename)
            if not parts:
                continue
            target = d.joinpath(*parts)
            if not inside(target, d):
                continue
            files += 1
            if files > MAX_DEPLOY_FILES:
                raise ValueError(f"That .zip has more than {MAX_DEPLOY_FILES} files.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(m) as src, open(target, "wb") as dst:
                while True:   # count real bytes, so a zip bomb cannot fill the disk
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DEPLOY_BYTES:
                        raise ValueError("That .zip unpacks to more than 2 GB.")
                    dst.write(chunk)


def drop_if_empty_site(slug):
    site = DB["sites"].get(slug)
    if site and site["type"] == "upload" and not site["deploys"]:
        stop_site(slug)
        DB["sites"].pop(slug, None)
        shutil.rmtree(SITES_DIR / slug, ignore_errors=True)
        save_db()


def finish_deploy(slug, did, note=""):
    part = partial_dir(slug, did)
    normalize_root(part)
    count, size = folder_stats(part)
    if count > MAX_DEPLOY_FILES or size > MAX_DEPLOY_BYTES:
        shutil.rmtree(part, ignore_errors=True)
        with lock:
            drop_if_empty_site(slug)
        raise ValueError("That upload is too large for LaunchPad (limit 2 GB or 20,000 files).")
    if count == 0:
        shutil.rmtree(part, ignore_errors=True)
        with lock:
            drop_if_empty_site(slug)
        raise ValueError("The upload had no usable files.")
    final = deploy_dir(slug, did)
    part.rename(final)
    with lock:
        site = DB["sites"][slug]
        site["deploys"].insert(0, {"id": did, "time": time.time(), "files": count, "size": size,
                                   "publish_dir": detect_publish_dir(final), "note": note})
        site["current"] = did
        site["updated"] = time.time()
        for old in site["deploys"][KEEP_DEPLOYS:]:
            shutil.rmtree(deploy_dir(slug, old["id"]), ignore_errors=True)
        site["deploys"] = site["deploys"][:KEEP_DEPLOYS]
        start_site(slug)
        save_db()
        return public_site(slug)


# ================================================================ dashboard
class DashHandler(Base):
    EXTRA = DASH_HEADERS

    def allowed_hosts(self):
        hosts = {f"localhost:{DASH_PORT}", f"127.0.0.1:{DASH_PORT}", f"[::1]:{DASH_PORT}"}
        if LAN_DASHBOARD:
            hosts |= {f"{ip}:{DASH_PORT}" for ip in lan_ips()}
        return hosts

    def guard(self, write):
        """Blocks DNS-rebinding and cross-site requests from other web pages."""
        host = (self.headers.get("Host") or "").lower()
        if host not in self.allowed_hosts():
            self.send(403, "Forbidden")
            return False
        if write:
            origin = self.headers.get("Origin")
            if origin and origin.lower() != f"http://{host}":
                self.send(403, "Forbidden")
                return False
            if not secrets.compare_digest((self.headers.get("X-LaunchPad-Token") or "").encode("utf-8", "replace"), TOKEN.encode()):
                self.json({"error": "This request did not come from the LaunchPad dashboard. Reload the page."}, 403)
                return False
        return True

    def do_OPTIONS(self):
        self.send(403, "Forbidden")

    def route(self):
        u = urlsplit(self.path)
        return unquote(u.path), parse_qs(u.query)

    def do_GET(self):
        if not self.guard(False):
            return
        path, q = self.route()
        if path in ("/", "/index.html"):
            page = DASHBOARD.read_bytes().replace(b"<head>", f'<head><meta name="lp-token" content="{TOKEN}">'.encode(), 1)
            return self.send(200, page)
        if path == "/api/info":
            return self.json({"ips": lan_ips(), "dash_port": DASH_PORT, "qr": qrcode is not None})
        if path == "/api/sites":
            with lock:
                sites = [public_site(s) for s in DB["sites"]]
            sites.sort(key=lambda s: s.get("updated", 0), reverse=True)
            return self.json({"sites": sites})
        m = re.fullmatch(r"/api/sites/([\w-]+)/(qr\.png|download)", path)
        if m and m.group(1) in DB["sites"]:
            slug = m.group(1)
            if m.group(2) == "qr.png":
                if qrcode is None:
                    return self.send(404, "QR codes need the optional qrcode package.")
                ip = (q.get("ip") or lan_ips())[0]
                buf = io.BytesIO()
                qrcode.make(f'http://{ip}:{DB["sites"][slug]["port"]}/', box_size=8, border=2).save(buf, "PNG")
                return self.send(200, buf.getvalue(), "image/png")
            root = site_root(slug)
            if not root or not root.exists():
                return self.send(404, "Nothing to download yet.")
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for p in root.rglob("*"):
                    rel = p.relative_to(root)
                    if p.is_file() and not any(x in SKIP_NAMES for x in rel.parts):
                        z.write(p, rel.as_posix())
            return self.send(200, buf.getvalue(), "application/zip",
                             {"Content-Disposition": f'attachment; filename="{slug}.zip"'})
        self.send(404, "Not found")

    def do_PUT(self):
        if not self.guard(True):
            return
        path, q = self.route()
        m = re.fullmatch(r"/api/deploy/([\w-]+)/([\w-]+)/(file|zip)", path)
        if not m:
            return self.send(404, "Not found")
        try:
            d = partial_dir(m.group(1), m.group(2))
            if m.group(3) == "zip":
                with tempfile.TemporaryFile() as tmp:
                    self.body_to_file(tmp)
                    tmp.seek(0)
                    extract_zip(tmp, d)
                return self.json({"ok": True})
            parts = clean_parts((q.get("path") or [""])[0])
            if not parts:
                self.body_to_file(io.BytesIO())
                return self.json({"ok": True, "skipped": True})
            target = d.joinpath(*parts)
            if not inside(target, d):
                raise ValueError("Bad file path.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "wb") as fh:
                self.body_to_file(fh)
            return self.json({"ok": True})
        except zipfile.BadZipFile:
            return self.json({"error": "That .zip file could not be opened."}, 400)
        except ValueError as e:
            return self.json({"error": str(e)}, 400)

    def do_POST(self):
        if not self.guard(True):
            return
        path, _ = self.route()
        body = self.body_json()
        try:
            if path == "/api/deploy/start":
                slug, did = begin_deploy(body.get("slug"), body.get("name"))
                return self.json({"slug": slug, "deploy": did})
            m = re.fullmatch(r"/api/deploy/([\w-]+)/([\w-]+)/(finish|cancel)", path)
            if m:
                slug, did = m.group(1), m.group(2)
                if m.group(3) == "cancel":
                    shutil.rmtree(partial_dir(slug, did), ignore_errors=True)
                    with lock:
                        drop_if_empty_site(slug)
                    return self.json({"ok": True})
                return self.json({"site": finish_deploy(slug, did, body.get("note", ""))})
            if path == "/api/link":
                return self.json({"site": self.link(body)})
            m = re.fullmatch(r"/api/sites/([\w-]+)/(settings|rollback)", path)
            if m and m.group(1) in DB["sites"]:
                fn = self.settings if m.group(2) == "settings" else self.rollback
                return self.json({"site": fn(m.group(1), body)})
            self.send(404, "Not found")
        except ValueError as e:
            self.json({"error": str(e)}, 400)

    def do_DELETE(self):
        if not self.guard(True):
            return
        path, _ = self.route()
        m = re.fullmatch(r"/api/sites/([\w-]+)", path)
        with lock:
            site = DB["sites"].pop(m.group(1), None) if m else None
            if not site:
                return self.send(404, "Not found")
            stop_site(m.group(1))
            if site["type"] != "linked":   # a linked folder on disk is never touched
                shutil.rmtree(SITES_DIR / m.group(1), ignore_errors=True)
            save_db()
        self.json({"ok": True})

    # ---- actions
    def link(self, body):
        raw = (body.get("path") or "").strip().strip('"')
        p = Path(os.path.expanduser(raw)) if raw else None
        if not p or not p.is_dir():
            raise ValueError("That folder was not found on this computer.")
        if too_broad(p):
            raise ValueError("For your safety, LaunchPad will not share a whole drive or your home folder. "
                             "Pick the project folder itself.")
        with lock:
            name = clean_name(body.get("name")) or clean_name(p.resolve().name)
            slug = unique_slug(slugify(name))
            DB["sites"][slug] = {"name": name, "type": "linked", "path": str(p.resolve()),
                                 "publish_dir": detect_publish_dir(p), "port": next_port(), "spa": False,
                                 "livereload": True, "deploys": [], "created": time.time(), "updated": time.time()}
            start_site(slug)
            save_db()
            return public_site(slug)

    def settings(self, slug, body):
        with lock:
            site = DB["sites"][slug]
            if clean_name(body.get("name")):
                site["name"] = clean_name(body["name"])
            for key in ("spa", "livereload"):
                if key in body:
                    site[key] = bool(body[key])
            if site["type"] == "linked" and "publish_dir" in body:
                site["publish_dir"] = safe_subdir(body["publish_dir"])
            try:
                port = int(body.get("port", site["port"]))
            except (TypeError, ValueError):
                raise ValueError("The port must be a number, for example 8105.")
            if port != site["port"]:
                if not 1024 <= port <= 65535:
                    raise ValueError("Pick a port between 1024 and 65535.")
                if port == DASH_PORT or port in {s["port"] for s in DB["sites"].values()} or not port_free(port):
                    raise ValueError(f"Port {port} is already in use.")
                stop_site(slug)
                site["port"] = port
            start_site(slug)
            site["updated"] = time.time()
            save_db()
            return public_site(slug)

    def rollback(self, slug, body):
        with lock:
            site = DB["sites"][slug]
            if not any(d["id"] == body.get("deploy") for d in site.get("deploys", [])):
                raise ValueError("That version no longer exists.")
            site["current"] = body["deploy"]
            site["updated"] = time.time()
            save_db()
            return public_site(slug)


# ================================================================ start
def cleanup_partials():
    for p in SITES_DIR.glob("*/deploys/*.partial"):
        shutil.rmtree(p, ignore_errors=True)
    with lock:
        for slug in list(DB["sites"]):
            drop_if_empty_site(slug)


def main():
    load_db()
    cleanup_partials()
    host = "0.0.0.0" if LAN_DASHBOARD else "127.0.0.1"
    try:
        dash = ThreadingHTTPServer((host, DASH_PORT), DashHandler)
    except OSError:
        print(f"\n  Port {DASH_PORT} is busy. LaunchPad may already be running: open http://localhost:{DASH_PORT}/")
        input("  Press Enter to close...")
        return
    dash.daemon_threads = True
    with lock:
        for slug in list(DB["sites"]):
            start_site(slug)
        save_db()
    ip = lan_ips()[0]
    print("\n  =========================================")
    print("   LaunchPad is running")
    print(f"   Dashboard : http://localhost:{DASH_PORT}/")
    print(f"   Wi-Fi IP  : {ip}  (phones use this)")
    print(f"   Apps live : {len(servers)}")
    print("   Close this window to stop LaunchPad.")
    print("  =========================================\n")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{DASH_PORT}/")).start()
    try:
        dash.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
