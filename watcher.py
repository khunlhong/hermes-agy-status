import json
import os
import subprocess
import time
from datetime import datetime, timezone, timedelta

DASHBOARD_DIR = os.path.expanduser("~/.hermes/status-dashboard")
STATUS_FILE = os.path.join(DASHBOARD_DIR, "status.json")
STATE_INPUT_FILE = os.path.expanduser("~/.hermes/job_progress.json")
TZ_TH = timezone(timedelta(hours=7))

def count_processes(keyword):
    # Try psutil first (cross-platform, reliable on Windows)
    try:
        import psutil
        cnt = 0
        kw = keyword.lower()
        for p in psutil.process_iter(['name', 'cmdline']):
            try:
                name = (p.info['name'] or '').lower()
                cmd = ' '.join(p.info['cmdline'] or []).lower()
                if kw in name or kw in cmd:
                    cnt += 1
            except Exception:
                pass
        return cnt
    except ImportError:
        pass

    # Fallback to pgrep (Unix) or tasklist (Windows)
    try:
        if os.name == 'nt':
            out = subprocess.check_output(f'tasklist /FI "IMAGENAME eq {keyword}*"', shell=True, text=True)
            return max(0, len(out.strip().splitlines()) - 3)
        else:
            out = subprocess.check_output(["pgrep", "-f", keyword], text=True)
            return len([line for line in out.strip().splitlines() if line])
    except Exception:
        return 0

def read_job_state():
    if os.path.exists(STATE_INPUT_FILE):
        try:
            with open(STATE_INPUT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Also check WORKSPACE_QUEUE.json as rich fallback
    ws_queue = r"D:\WORK SPACE\WORKSPACE_QUEUE.json"
    if os.path.exists(ws_queue):
        try:
            with open(ws_queue, "r", encoding="utf-8") as f:
                q = json.load(f)
                agy_q = q.get("active_queues", {}).get("agy-pc", [])
                for item in agy_q:
                    if item.get("status") in ("translating_active_x20", "queued_for_translation") and item.get("completed_chapters", 0) > 0:
                        return {
                            "project": item.get("story_th") or item.get("story_cn"),
                            "step": f"กำลังแปล ({item.get('completed_chapters')}/{item.get('total_chapters')})",
                            "completed": item.get("completed_chapters", 0),
                            "total": item.get("total_chapters", 0),
                            "logs": [f"[{datetime.now(TZ_TH).strftime('%H:%M:%S')}] กำลังแปล {item.get('story_cn')}"]
                        }
        except Exception:
            pass
    return {}

def build_status():
    hermes_procs = count_processes("hermes")
    agy_procs = count_processes("agy") or count_processes("auto_queue_runner")
    job = read_job_state()

    now_str = datetime.now(TZ_TH).isoformat(timespec="seconds")
    return {
        "updated_at": now_str,
        "hermes_status": "ONLINE" if hermes_procs > 0 else "IDLE",
        "agy_status": "WORKING" if agy_procs > 0 else "IDLE",
        "agy_active_workers": agy_procs if agy_procs > 0 else (20 if "แปล" in str(job.get("step")) else 0),
        "current_project": job.get("project", "Hermes + AGY Industrial Pipeline"),
        "current_step": job.get("step", "กำลังประมวลผลงานแปลอัตโนมัติ..."),
        "completed_count": job.get("completed", 0),
        "total_count": job.get("total", 0),
        "recent_logs": job.get("logs", [f"[{now_str}] ระบบตรวจสอบทำงานปกติ (0 Token)"])[-10:]
    }

def push_to_github():
    subprocess.run(["git", "-C", DASHBOARD_DIR, "add", "status.json"], check=False)
    diff = subprocess.run(["git", "-C", DASHBOARD_DIR, "diff", "--cached", "--quiet"])
    if diff.returncode != 0:
        subprocess.run(["git", "-C", DASHBOARD_DIR, "commit", "-m", "chore: update live status [skip ci]"], check=False)
        subprocess.run(["git", "-C", DASHBOARD_DIR, "push", "origin", "main"], check=False)

if __name__ == "__main__":
    last_snapshot = None
    while True:
        try:
            current = build_status()
            compare_key = (
                current["hermes_status"],
                current["agy_status"],
                current["current_project"],
                current["current_step"],
                current["completed_count"],
                current["total_count"]
            )
            if compare_key != last_snapshot:
                with open(STATUS_FILE, "w", encoding="utf-8") as f:
                    json.dump(current, f, ensure_ascii=False, indent=2)
                push_to_github()
                last_snapshot = compare_key
        except Exception as e:
            print(f"Watcher loop error: {e}", flush=True)
        time.sleep(10)
