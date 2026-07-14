import urllib.request
import json
import time
import concurrent.futures
import sys

BASE_URL = "http://127.0.0.1:8081/api"

def make_request(url, data=None, headers=None, method=None):
    if headers is None:
        headers = {}
    if data is not None and "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"
        
    if method is None:
        method = "POST" if data is not None else "GET"
        
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8") if data else None,
        headers=headers,
        method=method
    )
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode())
        except Exception:
            err_body = e.reason
        return e.code, err_body
    except Exception as e:
        return 0, str(e)

def login():
    code, res = make_request(f"{BASE_URL}/auth/login", data={"username": "admin", "password": "admin123"})
    if code == 200:
        return res["access_token"]
    raise Exception(f"Login failed: {res}")

def run_stress_test(token):
    print("--- Running Scenario A: Concurrency Stress Test (10 concurrent requests) ---")
    presets = ["success", "missing_column", "unexpected_column", "type_error"]
    
    def trigger_run(i):
        preset = presets[i % len(presets)]
        data = {
            "preset_name": preset,
            "target_table": "user_activities",
            "target_database": "default"
        }
        start = time.time()
        code, res = make_request(f"{BASE_URL}/upload/simulate", data=data)
        elapsed = time.time() - start
        return i, preset, code, res, elapsed

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(trigger_run, i) for i in range(10)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
    success_count = sum(1 for r in results if r[2] == 200)
    print(f"Triggered 10 runs concurrently. Successful submissions: {success_count}/10")
    
    # Wait for processing to settle
    time.sleep(5)
    
    # Query final status of the jobs
    headers = {"Authorization": f"Bearer {token}"}
    stats = []
    for r in results:
        if r[2] != 200:
            continue
        job_id = r[3]["id"]
        code, job = make_request(f"{BASE_URL}/jobs/{job_id}", headers=headers)
        if code == 200:
            stats.append(job)
            print(f"  Job {job_id} ({r[1]} preset): Status = {job['status']}, Duration = {job['duration_ms']}ms")
            
    return stats

def test_rate_limiter():
    print("\n--- Running Scenario B: Rate Limiter Integrity Test (1005 rapid requests) ---")
    triggered_429 = False
    rate_429_count = 0
    total_calls = 1005
    
    start_time = time.time()
    for i in range(total_calls):
        # We call a simple open endpoint
        code, res = make_request(f"{BASE_URL}/upload/notifications")
        if code == 429:
            triggered_429 = True
            rate_429_count += 1
            
    elapsed = time.time() - start_time
    print(f"Executed {total_calls} requests in {elapsed:.2f} seconds.")
    print(f"Rate Limiter Triggered 429: {triggered_429} (Count: {rate_429_count})")
    return triggered_429, rate_429_count

def main():
    print("=============================================================")
    print("      SENIOR QA PERFORMANCE & STRESS HARNESS REPORT          ")
    print("=============================================================\n")
    
    try:
        token = login()
    except Exception as e:
        print(f"CRITICAL ERROR: Cannot login. Is the server running? Details: {e}")
        sys.exit(1)
        
    start_all = time.time()
    
    # 1. Run stress concurrency tests
    jobs_stats = run_stress_test(token)
    
    # 2. Run rate limiter test
    rl_triggered, rl_count = test_rate_limiter()
    
    # 3. Calculate latency metrics
    print("\n=============================================================")
    print("                 BENCHMARK METRICS SUMMARY                  ")
    print("=============================================================")
    if jobs_stats:
        completed = [j for j in jobs_stats if j["status"] == "COMPLETED"]
        quarantined = [j for j in jobs_stats if j["status"] == "QUARANTINED"]
        
        avg_completed_ms = sum(j["duration_ms"] for j in completed) / len(completed) if completed else 0
        avg_quarantined_ms = sum(j["duration_ms"] for j in quarantined) / len(quarantined) if quarantined else 0
        
        print(f"Total processed runs under concurrency: {len(jobs_stats)}")
        print(f"  - Completed (Success): {len(completed)}")
        print(f"  - Quarantined (Failures): {len(quarantined)}")
        print(f"Mean processing time (Successful runs): {avg_completed_ms:.1f} ms")
        print(f"Mean processing time (Quarantined runs): {avg_quarantined_ms:.1f} ms")
    else:
        print("No job stats available.")
        
    print(f"Rate Limiter protection status: {'PASSED' if rl_triggered else 'FAILED'}")
    print(f"Test Execution Duration: {time.time() - start_all:.2f} seconds")
    print("=============================================================\n")

if __name__ == "__main__":
    main()
