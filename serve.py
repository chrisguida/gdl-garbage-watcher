#!/usr/bin/env python3
"""Local-dev mirror of the Vercel function: serves index.html and proxies
/api/posiciones to the GDL API (HTTPS-with-bypass for the expired cert)."""
import http.server, socketserver, ssl, urllib.request, json

API = "https://tequierolimpiapi.guadalajara.gob.mx/caabsa/posiciones"
PORT = 8765

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/posiciones"):
            try:
                req = urllib.request.Request(API, headers={"User-Agent": "Mozilla/5.0 proxy"})
                with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
                    body = r.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_error(502, f"upstream: {e}")
            return
        super().do_GET()

with socketserver.ThreadingTCPServer(("", PORT), H) as srv:
    print(f"serving on http://localhost:{PORT}/")
    srv.serve_forever()
