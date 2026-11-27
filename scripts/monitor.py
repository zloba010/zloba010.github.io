#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TroubleTab Ecosystem Monitor
Собирает метрики доступности, деплои, коммиты и запуски workflow.
Результат: uptime-data.json (история 24ч + дневные сводки 400д + инциденты).
"""
import json, os, time, datetime, urllib.request, urllib.error, urllib.parse

OWNER = os.environ.get("GITHUB_REPOSITORY", "zloba010/zloba010.github.io").split("/")[0]
REPO_SELF = os.environ.get("GITHUB_REPOSITORY", "zloba010/zloba010.github.io")
TOKEN = os.environ.get("MONITOR_TOKEN") or os.environ.get("GH_TOKEN")
DATA_FILE = "uptime-data.json"

SITES = [
    {"name": "Root",            "url": "https://zloba010.github.io/",                                      "repo": "zloba010.github.io"},
    {"name": "KFWR",            "url": "https://zloba010.github.io/KFWR---Kizami-Free-Web-Reader/",         "repo": "KFWR---Kizami-Free-Web-Reader"},
    {"name": "Kizamia Notes",   "url": "https://zloba010.github.io/kizamianotes/",                          "repo": "kizamianotes"},
    {"name": "Upscale Image",   "url": "https://zloba010.github.io/KizamiaUpscaleImage/",                   "repo": "KizamiaUpscaleImage"},
    {"name": "Kizamia Weather", "url": "https://zloba010.github.io/Kizamia-Weather/",                       "repo": "Kizamia-Weather"},
]

HISTORY_KEEP = 288      # 24 часа при интервале 5 минут
DAILY_KEEP   = 400      # ~13 месяцев дневных сводок
INC_KEEP     = 80       # последние инциденты
NOW = datetime.datetime.now(datetime.timezone.utc)
NOW_ISO = NOW.isoformat()

# ---------- HTTP ----------
def http_get(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def gh_api(path, per_page=20):
    if not TOKEN: return []
    url = f"https://api.github.com{path}{'&' if '?' in path else '?'}per_page={per_page}"
    try:
        return http_get(url, {"Authorization": f"token {TOKEN}",
                              "Accept": "application/vnd.github+json",
                              "User-Agent": "troubletab-monitor"})
    except Exception:
        return []

def ping(url):
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "troubletab-monitor"})
        with urllib.request.urlopen(req, timeout=10) as r:
            code = r.getcode()
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception:
        code = 0
    ms = int((time.time() - t0) * 1000)
    return code, ms, (200 <= code < 400)

def iso(dt): return dt.isoformat()
def parse_dt(s):
    try: return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception: return NOW

# ---------- загрузка ----------
if os.path.exists(DATA_FILE):
    try: data = json.load(open(DATA_FILE, encoding="utf-8"))
    except Exception: data = {}
else: data = {}
data.setdefault("last_updated", "")
data.setdefault("sites", {})

open_incidents = {}   # site -> incident dict (для продолжения незакрытых)

for site in SITES:
    name, url, repo = site["name"], site["url"], site["repo"]
    code, ms, ok = ping(url)
    status = "up" if ok else "down"
    s = data["sites"].setdefault(name, {
        "url": url, "repo": repo, "history": [], "daily": [],
        "incidents": [], "deploys": [], "commits": [], "runs": [],
        "current_status": status, "current_code": code, "current_ms": ms,
    })
    s.update({"url": url, "repo": repo, "current_status": status,
              "current_code": code, "current_ms": ms, "current_time": NOW_ISO})

    # --- история (24ч) ---
    s["history"].append({"time": NOW_ISO, "status": status, "ms": ms, "code": code})
    s["history"] = s["history"][-HISTORY_KEEP:]

    # --- дневная сводка ---
    day = NOW.strftime("%Y-%m-%d")
    d = next((x for x in s["daily"] if x["date"] == day), None)
    if not d:
        d = {"date": day, "checks": 0, "up": 0, "errors": 0, "sum_ms": 0,
             "max_ms": 0, "downtime_s": 0, "deploys": 0}
        s["daily"].append(d)
    d["checks"] += 1; d["up"] += 1 if ok else 0; d["errors"] += 0 if ok else 1
    d["sum_ms"] += ms; d["max_ms"] = max(d["max_ms"], ms)
    s["daily"] = s["daily"][-DAILY_KEEP:]

    # --- инциденты ---
    prev = s["history"][-2]["status"] if len(s["history"]) > 1 else status
    if prev == "up" and status == "down":
        inc = {"start": NOW_ISO, "end": None, "code": code, "site": name}
        s["incidents"].append(inc)
    if status == "down":
        last_open = next((i for i in reversed(s["incidents"]) if i["end"] is None), None)
        if last_open:
            minutes = (NOW - parse_dt(last_open["start"])).total_seconds() / 60
            last_open["minutes"] = round(minutes, 1)

    # --- деплои GitHub Pages (длительность обновления) ---
    deps = gh_api(f"/repos/{OWNER}/{repo}/pages/deployments", 10)
    dep_list = []
    for dep in deps:
        created = parse_dt(dep.get("created_at", NOW_ISO))
        updated = parse_dt(dep.get("updated_at", NOW_ISO))
        dur = max(0, int((updated - created).total_seconds()))
        # сколько секунд сайт был недоступен именно во время этого деплоя
        down_during = 0
        for h in s["history"]:
            t = parse_dt(h["time"])
            if created <= t <= updated and h["status"] == "down":
                down_during += 5 * 60
        dep_list.append({
            "id": dep.get("id"), "status": dep.get("status"),
            "created_at": dep.get("created_at"), "updated_at": dep.get("updated_at"),
            "duration_s": dur, "down_during_s": down_during,
            "sha": (dep.get("commit_sha") or "")[:7],
            "url": dep.get("url", ""),
        })
    s["deploys"] = dep_list[:10]

    # --- коммиты (что обновлялось) ---
    commits = gh_api(f"/repos/{OWNER}/{repo}/commits", 15)
    s["commits"] = [{
        "sha": c["sha"][:7], "date": c["commit"]["author"]["date"],
        "author": c["commit"]["author"]["name"],
        "msg": c["commit"]["message"].split("\n")[0][:140],
    } for c in commits][:15]

    # --- запуски workflow (как долго шло обновление) ---
    runs = gh_api(f"/repos/{OWNER}/{repo}/actions/runs", 12)
    s["runs"] = []
    for r in runs:
        if r.get("event") == "schedule" and "Ecosystem" in r.get("name", ""):
            continue  # не показываем сам мониторинг
        st, en = parse_dt(r.get("created_at") or NOW_ISO), parse_dt(r.get("updated_at") or NOW_ISO)
        s["runs"].append({
            "name": r.get("name", ""), "status": r.get("status"),
            "conclusion": r.get("conclusion"), "event": r.get("event"),
            "created_at": r.get("created_at"), "duration_s": max(0, int((en - st).total_seconds())),
            "url": r.get("html_url", ""),
        })
    s["runs"] = s["runs"][:12]

    # --- привязка инцидентов к деплоям (причина = обновление) ---
    for inc in s["incidents"]:
        if inc.get("deploy_sha"): continue
        st = parse_dt(inc["start"])
        for dep in s["deploys"]:
            if dep["created_at"] and parse_dt(dep["created_at"]) <= st <= parse_dt(dep["updated_at"] or dep["created_at"]):
                inc["deploy_sha"] = dep["sha"]; break

    s["incidents"] = s["incidents"][-INC_KEEP:]

data["last_updated"] = NOW_ISO
json.dump(data, open(DATA_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("Мониторинг завершён:", NOW_ISO)

# ---------- алерты через Issues (только свой репозиторий, GITHUB_TOKEN) ----------
def gh_issues_api(path, method="GET", body=None):
    tok = os.environ.get("GH_TOKEN")
    if not tok: return
    req = urllib.request.Request(f"https://api.github.com{path}", method=method,
        headers={"Authorization": f"token {tok}", "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "User-Agent": "troubletab-monitor"},
        data=json.dumps(body).encode() if body else None)
    try: urllib.request.urlopen(req, timeout=15)
    except Exception: pass

for site in SITES:
    name = site["name"]; s = data["sites"].get(name, {})
    title = f"🚨 Сайт недоступен: {name}"
    if s.get("current_status") == "down":
        existing = gh_api(f"/repos/{REPO_SELF}/issues?state=open")
        if not any(i["title"] == title for i in existing):
            gh_issues_api(f"/repos/{REPO_SELF}/issues", "POST", {
                "title": title, "labels": ["monitoring-alert"],
                "body": f"**{name}** вернул код `{s.get('current_code')}`.\nВремя: `{NOW_ISO}`\nОтклик: `{s.get('current_ms')} мс`"})
    else:
        for i in gh_api(f"/repos/{REPO_SELF}/issues?state=open"):
            if i["title"] == title:
                gh_issues_api(i["url"], "PATCH", {"state": "closed"})
                gh_issues_api(i["url"] + "/comments", "POST",
                              {"body": f"✅ {name} снова доступен."})
