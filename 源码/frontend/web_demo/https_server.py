import http.server
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:17608").rstrip("/")
FRONTEND_HOST = os.getenv("FRONTEND_HOST", "0.0.0.0")
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "18094"))
FRONTEND_PUBLIC_HOST = os.getenv("FRONTEND_PUBLIC_HOST", "www.nstl.gov.cn")
FRONTEND_HTTPS = os.getenv("FRONTEND_HTTPS", "1").lower() in {"1", "true", "yes", "on"}
CERT_FILE = os.getenv("FRONTEND_CERT_FILE", "cert.pem")
KEY_FILE = os.getenv("FRONTEND_KEY_FILE", "key.pem")
API_PREFIXES = ("/v1/", "/system/", "/api/service/")


def _normalize_frontend_base(path):
    normalized = (path or "/").strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if not normalized.endswith("/"):
        normalized = f"{normalized}/"
    return normalized


FRONTEND_BASE_PATH = _normalize_frontend_base(
    os.getenv("FRONTEND_BASE_PATH", "/ai/agent/claim_consistency/")
)

os.chdir(os.path.dirname(os.path.abspath(__file__)))


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    """Static file server plus API reverse proxy."""

    def do_GET(self):
        redirect_url = self._frontend_redirect_url()
        if redirect_url:
            self._redirect(redirect_url)
        elif self._is_api():
            self._proxy()
        else:
            super().do_GET()

    def do_POST(self):
        if self._is_api():
            self._proxy()
        else:
            self.send_error(405)

    def do_PUT(self):
        if self._is_api():
            self._proxy()
        else:
            self.send_error(405)

    def do_DELETE(self):
        if self._is_api():
            self._proxy()
        else:
            self.send_error(405)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _is_api(self):
        return self._proxy_path() is not None

    def _proxy(self):
        url = BACKEND_URL + self._proxy_path()
        body = None
        content_length = self.headers.get("Content-Length")
        if content_length:
            body = self.rfile.read(int(content_length))

        req = urllib.request.Request(url, data=body, method=self.command)
        for header in ("Content-Type", "X-User-Scope", "Authorization"):
            value = self.headers.get(header)
            if value:
                req.add_header(header, value)

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                self.send_response(resp.status)
                self._cors_headers()
                content_type = resp.headers.get("Content-Type", "")
                if content_type:
                    self.send_header("Content-Type", content_type)
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as exc:
            self.send_response(exc.code)
            self._cors_headers()
            content_type = exc.headers.get("Content-Type", "")
            if content_type:
                self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(exc.read())
        except Exception as exc:
            self.send_response(502)
            self._cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(f'{{"error":"proxy error: {exc}"}}'.encode("utf-8"))

    def _cors_headers(self):
        origin = self.headers.get("Origin", "*")
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-User-Scope,Authorization")
        self.send_header("Access-Control-Allow-Credentials", "true")

    def _proxy_path(self):
        if urllib.parse.urlsplit(self.path).path.startswith(API_PREFIXES):
            return self.path
        stripped_path = self._strip_frontend_base(self.path)
        if urllib.parse.urlsplit(stripped_path).path.startswith(API_PREFIXES):
            return stripped_path
        return None

    def _strip_frontend_base(self, path):
        parts = urllib.parse.urlsplit(path)
        request_path = parts.path
        base_without_slash = FRONTEND_BASE_PATH.rstrip("/")
        if request_path == base_without_slash or request_path == FRONTEND_BASE_PATH:
            stripped_path = "/"
        elif request_path.startswith(FRONTEND_BASE_PATH):
            stripped_path = "/" + request_path[len(FRONTEND_BASE_PATH):].lstrip("/")
        else:
            stripped_path = request_path
        return urllib.parse.urlunsplit(("", "", stripped_path, parts.query, parts.fragment))

    def _frontend_redirect_url(self):
        parts = urllib.parse.urlsplit(self.path)
        request_path = parts.path
        if request_path in {"/", "/index.html"}:
            target_path = FRONTEND_BASE_PATH
        elif request_path == FRONTEND_BASE_PATH.rstrip("/"):
            target_path = FRONTEND_BASE_PATH
        else:
            return None
        return urllib.parse.urlunsplit(("", "", target_path, parts.query, parts.fragment))

    def _redirect(self, url):
        self.send_response(308)
        self.send_header("Location", url)
        self.end_headers()

    def translate_path(self, path):
        return super().translate_path(self._strip_frontend_base(path))

    def log_message(self, format, *args):
        print(f"[{FRONTEND_PORT}] {format % args}")


server_address = (FRONTEND_HOST, FRONTEND_PORT)
httpd = http.server.HTTPServer(server_address, ProxyHandler)

scheme = "http"
mode = "HTTP"
if FRONTEND_HTTPS:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    scheme = "https"
    mode = "HTTPS"

print(f"{mode} server running on {scheme}://{FRONTEND_PUBLIC_HOST}:{FRONTEND_PORT}{FRONTEND_BASE_PATH}")
print(f"API proxy forwards {API_PREFIXES} to {BACKEND_URL}")
httpd.serve_forever()
