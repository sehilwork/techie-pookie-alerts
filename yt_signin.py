# One-time Google sign-in for the daily exact YouTube subscriber count (read-only YouTube Analytics access).
# Run on the owner's Mac: python3 yt_signin.py  -> prints a sign-in URL, waits on 127.0.0.1 for Google's redirect,
# then saves the refresh token to ~/.config/techie-pookie/yt_refresh_token (never printed).
# Client id/secret come from ~/.config/techie-pookie/yt_client_id and yt_client_secret (Desktop OAuth client).
import base64, hashlib, http.server, json, os, secrets, sys, urllib.parse, urllib.request
try:
    import certifi; os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass

D = os.path.expanduser("~/.config/techie-pookie")
CID, SECRET = (open(f"{D}/{n}").read().strip() for n in ("yt_client_id", "yt_client_secret"))
SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
verifier = secrets.token_urlsafe(64)
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
state = secrets.token_urlsafe(16)
got = {}

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
        ok = q.get("state") == state and "code" in q
        if ok:
            got["code"] = q["code"]
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(("<h2>Done — you can close this tab.</h2>" if ok else f"<h2>Sign-in failed: {q.get('error', 'unknown')}</h2>").encode())
    def log_message(self, *a):
        pass

srv = http.server.HTTPServer(("127.0.0.1", 0), H)
redirect = f"http://127.0.0.1:{srv.server_port}"
url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
    "client_id": CID, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE, "access_type": "offline",
    "prompt": "consent", "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    "login_hint": "techiepookie@gmail.com"})
print(url, flush=True)
srv.timeout = 900
while "code" not in got:
    srv.handle_request()
r = json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", urllib.parse.urlencode({
    "code": got["code"], "client_id": CID, "client_secret": SECRET, "redirect_uri": redirect,
    "grant_type": "authorization_code", "code_verifier": verifier}).encode(), timeout=30))
if "refresh_token" not in r:
    sys.exit("no refresh token returned")
old = os.umask(0o077)
open(f"{D}/yt_refresh_token", "w").write(r["refresh_token"])
os.umask(old)
print("saved refresh token", flush=True)
