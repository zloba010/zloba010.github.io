#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, time, datetime, urllib.request, urllib.error

OWNER = "zloba010"
TOKEN = os.environ.get("MONITOR_TOKEN") or os.environ.get("GH_TOKEN")
DATA_FILE = "uptime-data.json"

SITES = [
    {
        "name": "Root",
        "url": "https://zloba010.github.io/",
        "repo": "zloba010.github.io",
        "checks": [
            {"type": "http", "expected": 200},
            {"type": "contains", "text": "Kizamia", "description": "Главная страница содержит 'Kizamia'"},
            {"type": "contains", "text": "<script", "description": "JavaScript загружается"}
        ]
    },
    {
        "name": "KFWR",
        "url": "https://zloba010.github.io/KFWR---Kizami-Free-Web-Reader/",
        "repo": "KFWR---Kizami-Free-Web-Reader",
        "checks": [
            {"type": "http", "expected": 200},
            {"type": "contains", "text": "reader", "description": "Читалка загружается"},
            {"type": "contains", "text": "<canvas", "description": "Canvas для читалки присутствует"}
        ]
    },
    {
        "name": "Kizamia Notes",
        "url": "https://zloba010.github.io/kizamianotes/",
        "repo": "kizamianotes",
        "checks": [
            {"type": "http", "expected": 200},
            {"type": "contains", "text": "note", "description": "Заметки загружаются"}
        ]
    },
    {
        "name": "Upscale Image",
        "url": "https://zloba010.github.io/KizamiaUpscaleImage/",
        "repo": "KizamiaUpscaleImage",
        "checks": [
            {"type": "http", "expected": 200},
            {"type": "contains", "text": "upscale", "description": "Апскейлер загружается"},
            {"type": "contains", "text": "input", "description": "Input для загрузки файлов присутствует"}
        ]
    },
    {
        "name": "Kizamia Weather",
        "url": "https://zloba010.github.io/Kizamia-Weather/",
        "repo": "Kizamia-Weather",
        "checks": [
            {"type": "http", "expected": 200},
            {"type": "contains", "text": "weather", "description": "Погода загружается"},
            {"type": "contains", "text": "temp", "description": "Блок с температурой присутствует"}
        ]
    },
]

HISTORY_KEEP = 288
DAILY_KEEP = 400
INC_KEEP = 80
LOGS_KEEP = 50
NOW = datetime.datetime.now(datetime.timezone.utc)
NOW_ISO = NOW.isoformat()

def http_get(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8"), r.getcode()

def gh_api(path, per_page=20):
    if not TOKEN:
        return []
    url = f"https://api.github.com{path}{'&' if '?' in path else '?'}per_page={per_page}"
    try:
        req = urllib.request.Request(url, headers={
            "Authorization": f"token {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "troubletab-monitor"
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"GitHub API error: {e}")
        return []

def ping(site):
    t0 = time.time()
    status_code = 0
    is_functional = True
    errors = []
    
    try:
        html, status_code = http_get(site["url"], {"User-Agent": "troubletab-monitor"}, timeout=10)
        
        for check in site.get("checks", []):
            if check["type"] == "contains":
                if check["text"].lower() not in html.lower():
                    is_functional = False
                    errors.append(check["description"])
    except urllib.error.HTTPError as e:
        status_code = e.code
        is_functional = False
        errors.append(f"HTTP {e.code}")
    except Exception as e:
        is_functional = False
        errors.append(str(e)[:100])
    
    ms = int((time.time() - t0) * 1000)
    ok = (status_code == 200) and is_functional
    
    return {
        "code": status_code,
        "ms": ms,
        "ok": ok,
        "is_functional": is_functional,
        "errors": errors
    }

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
data.setdefault("critical_issues", [])
data.setdefault("logs", [])

critical_issues = []
new_logs = []

new_logs.append({"time": NOW_ISO, "site": "Монитор", "action": f"Запуск проверки {len(SITES)} сервисов", "status": "info"})

for site in SITES:
    name = site["name"]
    url = site["url"]
    repo = site["repo"]
    
    new_logs.append({"time": NOW_ISO, "site": name, "action": "Начало проверки", "status": "info"})
    
    result = ping(site)
    status = "up" if result["ok"] else "down"
    
    if not result["ok"]:
        new_logs.append({"time": NOW_ISO, "site": name, "action": f"Ошибка: {', '.join(result['errors'])}", "status": "error"})
    else:
        new_logs.append({"time": NOW_ISO, "site": name, "action": f"Проверка завершена: {result['code']}, {result['ms']}мс", "status": "success"})
    
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
            "current_code": result["code"],
            "current_ms": result["ms"],
            "is_functional": result["is_functional"],
            "errors": result["errors"],
        }
    
    s = data["sites"][name]
    s.setdefault("history", [])
    s.setdefault("daily", [])
    s.setdefault("incidents", [])
    s.setdefault("deploys", [])
    s.setdefault("commits", [])
    s.setdefault("runs", [])
    s.setdefault("is_functional", True)
    s.setdefault("errors", [])
    
    s["url"] = url
    s["repo"] = repo
    s["current_status"] = status
    s["current_code"] = result["code"]
    s["current_ms"] = result["ms"]
    s["current_time"] = NOW_ISO
    s["is_functional"] = result["is_functional"]
    s["errors"] = result["errors"]
    
    if not result["ok"]:
        critical_issues.append({
            "site": name,
            "repo": repo,
            "url": url,
            "status": result["code"],
            "errors": result["errors"],
            "time": NOW_ISO
        })
    
    s["history"].append({
        "time": NOW_ISO,
        "status": status,
        "ms": result["ms"],
        "code": result["code"],
        "is_functional": result["is_functional"]
    })
    s["history"] = s["history"][-HISTORY_KEEP:]
    
    day = NOW.strftime("%Y-%m-%d")
    d = next((x for x in s["daily"] if x["date"] == day), None)
    if not d:
        d = {"date": day, "checks": 0, "up": 0, "errors": 0, "sum_ms": 0, "max_ms": 0}
        s["daily"].append(d)
    d["checks"] += 1
    d["up"] += 1 if result["ok"] else 0
    d["errors"] += 0 if result["ok"] else 1
    d["sum_ms"] += result["ms"]
    d["max_ms"] = max(d["max_ms"], result["ms"])
    s["daily"] = s["daily"][-DAILY_KEEP:]
    
    prev = s["history"][-2]["status"] if len(s["history"]) > 1 else status
    if prev == "up" and status == "down":
        s["incidents"].append({"start": NOW_ISO, "end": None, "code": result["code"], "site": name})
        new_logs.append({"time": NOW_ISO, "site": name, "action": "Зафиксирован инцидент", "status": "warning"})
    
    for inc in s["incidents"]:
        if inc["end"] is None:
            minutes = (NOW - parse_dt(inc["start"])).total_seconds() / 60
            inc["minutes"] = round(minutes, 1)
    
    s["incidents"] = s["incidents"][-INC_KEEP:]
    
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
                })
            s["deploys"] = dep_list[:10]
        except Exception as e:
            print(f"Error fetching deploys for {name}: {e}")
    
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
                })
            s["runs"] = s["runs"][:12]
        except Exception as e:
            print(f"Error fetching runs for {name}: {e}")

new_logs.append({"time": NOW_ISO, "site": "Монитор", "action": f"Проверка завершена: {len(critical_issues)} критических ошибок", "status": "success" if not critical_issues else "error"})

data["last_updated"] = NOW_ISO
data["critical_issues"] = critical_issues
data["logs"] = (data.get("logs", []) + new_logs)[-LOGS_KEEP:]

with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"✅ Мониторинг завершён: {NOW_ISO}")
print(f"Проверено сайтов: {len(SITES)}")
for site in SITES:
    s = data["sites"][site["name"]]
    func = "✓" if s["is_functional"] else "✗"
    print(f"  {site['name']}: {s['current_status']} ({s['current_code']}, {s['current_ms']}ms) [{func}]")
if critical_issues:
    print(f"\n⚠️ Критические ошибки: {len(critical_issues)}")
    for issue in critical_issues:
        print(f"  - {issue['site']}: {', '.join(issue['errors'])}")
