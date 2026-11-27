#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, time, datetime, urllib.request, urllib.error

OWNER = "zloba010"
REPO_SELF = "zloba010/zloba010.github.io"
TOKEN = os.environ.get("MONITOR_TOKEN") or os.environ.get("GH_TOKEN")
DATA_FILE = "uptime-data.json"

SITES = [
    {"name": "Root", "url": "https://zloba010.github.io/", "repo": "zloba010.github.io"},
    {"name": "KFWR", "url": "https://zloba010.github.io/KFWR---Kizami-Free-Web-Reader/", "repo": "KFWR---Kizami-Free-Web-Reader"},
    {"name": "Kizamia Notes", "url": "https://zloba010.github.io/kizamianotes/", "repo": "kizamianotes"},
    {"name": "Upscale Image", "url": "https://zloba010.github.io/KizamiaUpscaleImage/", "repo": "KizamiaUpscaleImage"},
    {"name": "Kizamia Weather", "url": "https://zloba010.github.io/Kizamia-Weather/", "repo": "Kizamia-Weather"},
]

HISTORY_KEEP = 288
DAILY_KEEP = 400
INC_KEEP = 80
NOW = datetime.datetime.now(datetime.timezone.utc)
NOW_ISO = NOW.isoformat()

def http_get(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def gh_api(path, per_page=20):
    if not TOKEN:
        return []
    url = f"https://api.github.com{path}{'&' if '?' in path else '?'}per_page={per_page}"
    try:
        return http_get(url, {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github+json", "User-Agent": "troubletab-monitor"})
    except Exception as e:
        print(f"GitHub API error: {e}")
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

def parse_dt(s):
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return NOW

# Загружаем существующие данные
if os.path.exists(DATA_FILE):
    try:
        data = json.load(open(DATA_FILE, encoding="utf-8"))
    except Exception:
        data = {}
else:
    data = {}

data.setdefault("last_updated", "")
data.setdefault("sites", {})

for site in SITES:
    name = site["name"]
    url = site["url"]
    repo = site["repo"]
    
    code, ms, ok = ping(url)
    status = "up" if ok else "down"
    
    # Инициализируем структуру сайта с защитой от старых данных
    if name not in data["sites"]:
        data["sites"][name] = {
            "url": url,
            "repo": repo,
            "history": [],
            "daily": [],
            "incidents": [],
            "deploys": [],
            "commits": [],
            "runs": [],
            "current_status": status,
            "current_code": code,
            "current_ms": ms,
        }
    
    s = data["sites"][name]
    
    # Миграция старых данных: добавляем отсутствующие поля
    s.setdefault("url", url)
    s.setdefault("repo", repo)
    s.setdefault("history", [])
    s.setdefault("daily", [])
    s.setdefault("incidents", [])
    s.setdefault("deploys", [])
    s.setdefault("commits", [])
    s.setdefault("runs", [])
    
    s["current_status"] = status
    s["current_code"] = code
    s["current_ms"] = ms
    s["current_time"] = NOW_ISO
    
    # История (24ч)
    s["history"].append({"time": NOW_ISO, "status": status, "ms": ms, "code": code})
    s["history"] = s["history"][-HISTORY_KEEP:]
    
    # Дневная сводка
    day = NOW.strftime("%Y-%m-%d")
    d = next((x for x in s["daily"] if x["date"] == day), None)
    if not d:
        d = {"date": day, "checks": 0, "up": 0, "errors": 0, "sum_ms": 0, "max_ms": 0, "downtime_s": 0, "deploys": 0}
        s["daily"].append(d)
    d["checks"] += 1
    d["up"] += 1 if ok else 0
    d["errors"] += 0 if ok else 1
    d["sum_ms"] += ms
    d["max_ms"] = max(d["max_ms"], ms)
    s["daily"] = s["daily"][-DAILY_KEEP:]
    
    # Инциденты
    prev = s["history"][-2]["status"] if len(s["history"]) > 1 else status
    if prev == "up" and status == "down":
        s["incidents"].append({"start": NOW_ISO, "end": None, "code": code, "site": name})
    
    # Обновляем длительность открытых инцидентов
    for inc in s["incidents"]:
        if inc["end"] is None:
            minutes = (NOW - parse_dt(inc["start"])).total_seconds() / 60
            inc["minutes"] = round(minutes, 1)
    
    s["incidents"] = s["incidents"][-INC_KEEP:]
    
    # Деплои (только если есть токен)
    if TOKEN:
        try:
            deps = gh_api(f"/repos/{OWNER}/{repo}/pages/deployments", 10)
            dep_list = []
            for dep in deps:
                created = parse_dt(dep.get("created_at", NOW_ISO))
                updated = parse_dt(dep.get("updated_at", NOW_ISO))
                dur = max(0, int((updated - created).total_seconds()))
                dep_list.append({
                    "id": dep.get("id"),
                    "status": dep.get("status"),
                    "created_at": dep.get("created_at"),
                    "updated_at": dep.get("updated_at"),
                    "duration_s": dur,
                    "sha": (dep.get("commit_sha") or "")[:7],
                    "url": dep.get("url", ""),
                })
            s["deploys"] = dep_list[:10]
        except Exception as e:
            print(f"Error fetching deploys for {name}: {e}")
    
    # Коммиты (только если есть токен)
    if TOKEN:
        try:
            commits = gh_api(f"/repos/{OWNER}/{repo}/commits", 15)
            s["commits"] = [{
                "sha": c["sha"][:7],
                "date": c["commit"]["author"]["date"],
                "author": c["commit"]["author"]["name"],
                "msg": c["commit"]["message"].split("\n")[0][:140],
            } for c in commits][:15]
        except Exception as e:
            print(f"Error fetching commits for {name}: {e}")
    
    # Runs (только если есть токен)
    if TOKEN:
        try:
            runs = gh_api(f"/repos/{OWNER}/{repo}/actions/runs", 12)
            s["runs"] = []
            for r in runs:
                if r.get("event") == "schedule" and "Ecosystem" in r.get("name", ""):
                    continue
                st = parse_dt(r.get("created_at") or NOW_ISO)
                en = parse_dt(r.get("updated_at") or NOW_ISO)
                s["runs"].append({
                    "name": r.get("name", ""),
                    "status": r.get("status"),
                    "conclusion": r.get("conclusion"),
                    "event": r.get("event"),
                    "created_at": r.get("created_at"),
                    "duration_s": max(0, int((en - st).total_seconds())),
                    "url": r.get("html_url", ""),
                })
            s["runs"] = s["runs"][:12]
        except Exception as e:
            print(f"Error fetching runs for {name}: {e}")

data["last_updated"] = NOW_ISO

# Сохраняем
with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"✅ Мониторинг завершён: {NOW_ISO}")
print(f"Проверено сайтов: {len(SITES)}")
for site in SITES:
    s = data["sites"][site["name"]]
    print(f"  {site['name']}: {s['current_status']} ({s['current_code']}, {s['current_ms']}ms)")
