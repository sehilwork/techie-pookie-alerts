# Techie Pookie follower alerts, run by GitHub Actions every 10 min (so they work while the owner's Mac is closed).
# Sends a Telegram message when YouTube subscribers or Instagram followers go above their highest count so far.
# Secrets (repo Settings → Secrets → Actions): TG_TOKEN, TG_CHAT, IG_TOKEN, YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN.
# Counts are kept in state.json (committed back).
# Exact YouTube count past 1,000 (where YouTube shows "1.2K"): YouTube Analytics gives exact daily gains/losses (owner-only,
# ~2-3 days late) but its lifetime sum misses older subscribers, so while the public count is still exact (<1,000) we record
# offset = public count - Analytics running total, and afterwards report Analytics running total + offset once a day.
import datetime, json, os, re, sys, urllib.error, urllib.parse, urllib.request

YT_URL = "https://www.youtube.com/channel/UCnhsSjyA80CfXgBvNm2KMbg"
IG_ID = "17841410007907238"  # @techie___pookie
STATE = "state.json"

def tg(text):
    data = urllib.parse.urlencode({"chat_id": os.environ["TG_CHAT"], "text": text}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage", data, timeout=30)

def youtube():
    req = urllib.request.Request(YT_URL, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    m = re.search(r"([\d.,]+)([KM]?) subscribers", html)
    # shortcut: YouTube shows exact counts only below 1,000 ("1.2K" after); switch to the YouTube Data API then
    return int(round(float(m.group(1).replace(",", "")) * {"": 1, "K": 1000, "M": 1000000}[m.group(2)])) if m else None

def instagram():
    q = urllib.parse.urlencode({"fields": "username,followers_count", "access_token": os.environ["IG_TOKEN"]})
    return json.load(urllib.request.urlopen(f"https://graph.facebook.com/v21.0/{IG_ID}?{q}", timeout=30))["followers_count"]

def rise(key, n, label, unit):
    """Alert once when n beats the best count seen (a 340->339->340 wobble does not re-alert)."""
    best = st.get(key)
    st[key] = max(n, best or 0)
    if best is None or n <= best:
        return
    tg(f"{label}\n+{n - best} , Total : {n:,} {unit}")

st = json.load(open(STATE)) if os.path.exists(STATE) else {}
n = None
try:
    n = youtube()
    if n:
        rise("yt_best", n, "YouTube", "subscribers")
except Exception as e:
    print("youtube skipped:", e)
try:
    rise("ig_best", instagram(), "Instagram", "followers")
    st.pop("ig_warned", None)
except urllib.error.HTTPError as e:
    print("instagram key error:", e.code)
    if e.code in (400, 401, 403) and not st.get("ig_warned"):
        st["ig_warned"] = True
        tg("⚠️ Instagram follower alerts stopped: the access key stopped working. Make a new one in "
           "Business settings → System users → follower-counter → Generate token, and update the IG_TOKEN secret on GitHub.")
except Exception as e:
    print("instagram skipped:", e)
def analytics(**p):
    tok = json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode(), timeout=30))["access_token"]
    u = "https://youtubeanalytics.googleapis.com/v2/reports?" + urllib.parse.urlencode(dict(ids="channel==MINE", **p))
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"Authorization": f"Bearer {tok}"}), timeout=30)).get("rows") or []

def youtube_exact(public):
    today = datetime.date.today()
    pub = st.setdefault("yt_public_by_day", {})
    if public and public < 1000:  # still exact on the channel page: remember the latest count for today (UTC)
        pub[str(today)] = public
    for d in sorted(pub)[:-14]:
        del pub[d]
    days = analytics(startDate=str(today - datetime.timedelta(10)), endDate=str(today),
                     metrics="subscribersGained,subscribersLost", dimensions="day")
    if not days:
        return
    last, gained, lost = days[-1]
    total = analytics(startDate="2005-01-01", endDate=last, metrics="subscribersGained,subscribersLost")[0]
    running = total[0] - total[1]
    if last in pub:
        st["yt_offset"] = pub[last] - running
    if "yt_offset" not in st or last <= st.get("yt_exact_day", ""):
        return
    exact = running + st["yt_offset"]
    st.update(yt_exact_day=last, yt_exact=exact)
    if (st.get("yt_best") or 0) >= 1000:  # below 1,000 the live alerts are already exact, so no daily message
        nice = datetime.date.fromisoformat(last).strftime("%-d %b")
        tg(f"📊 YouTube exact count: {exact:,} subscribers (as of {nice}: +{gained} new, −{lost} left). "
           "YouTube reports this 2–3 days late.")

try:
    youtube_exact(n)
except Exception as e:
    print("youtube exact skipped:", e)
json.dump(st, open(STATE, "w"), indent=1, sort_keys=True)
print(st)
