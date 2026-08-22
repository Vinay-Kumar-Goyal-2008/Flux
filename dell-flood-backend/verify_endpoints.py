import requests
import time
import sys

BASE_URL = "http://localhost:8000"

def test_root():
    print("Testing Root URL...")
    res = requests.get(f"{BASE_URL}/")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert data["status"] == "ONLINE", f"Expected ONLINE, got {data['status']}"
    print("✓ Root URL verified successfully!")

def test_preview():
    print("Testing Preview Satellite Images Endpoint...")
    res = requests.get(f"{BASE_URL}/api/preview?lat=25.6124&lon=85.1376")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert "optical_preview" in data, "Missing optical_preview field"
    assert "sar_preview" in data, "Missing sar_preview field"
    print("✓ Preview endpoint verified successfully!")

def test_detection_pipeline():
    print("Testing Detection Pipeline Endpoint...")
    res = requests.post(f"{BASE_URL}/api/run-detection?lat=25.6124&lon=85.1376&cloud_cover=12.0")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    job_id = res.json().get("job_id")
    assert job_id is not None, "Did not get a job_id back"
    print(f"Dispatched job. Job ID: {job_id}. Polling status...")
    
    # Poll status
    for _ in range(30):
        status_res = requests.get(f"{BASE_URL}/api/status/{job_id}")
        assert status_res.status_code == 200, f"Expected 200 status, got {status_res.status_code}"
        job_data = status_res.json()
        print(f"Current Status: {job_data['status']}, current_step: {job_data['current_step']}")
        if job_data["status"] == "complete":
            print("✓ Detection pipeline complete! Result:")
            print(job_data["result"])
            return job_data["result"]
        elif job_data["status"] == "failed":
            raise AssertionError(f"Job failed: {job_data.get('error')}")
        time.sleep(1.0)
    raise TimeoutError("Job took too long to complete")

def test_crowd_report():
    print("Testing Crowd Report Endpoint...")
    payload = {
        "username": "saif",
        "lat": 25.6124,
        "lon": 85.1376,
        "severity": "SEVERE",
        "description": "Rising water in the local market"
    }
    res = requests.post(f"{BASE_URL}/api/report-flood", json=payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert res.json()["status"] == "SUCCESS", "Expected status SUCCESS"
    print("✓ Crowd report submitted successfully!")

def test_complaints_list():
    print("Testing Complaints List Endpoint...")
    res = requests.get(f"{BASE_URL}/api/complaints/list")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert "complaints" in data, "Missing complaints field"
    assert "shelters" in data, "Missing shelters field"
    assert len(data["complaints"]) > 0, "No complaints found in database"
    print("✓ Complaints and shelters list verified successfully!")

def test_agent_cycle():
    print("Testing Agent Cycle Trigger...")
    payload = {
        "location": "Muzaffarpur",
        "lat": 26.1220,
        "lon": 85.3620,
        "phones": ["+917678656930"]
    }
    res = requests.post(f"{BASE_URL}/api/agent-cycle", json=payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert res.json()["status"] == "QUEUED", "Expected status QUEUED"
    print("✓ Agent cycle queued successfully! Waiting for agent reflection log...")
    
    # Poll for agent trace
    for _ in range(15):
        trace_res = requests.get(f"{BASE_URL}/api/agent-trace?location=Muzaffarpur")
        assert trace_res.status_code == 200, f"Expected 200, got {trace_res.status_code}"
        trace_data = trace_res.json()
        if trace_data.get("status") != "NO_TRACE":
            print("✓ Agent trace acquired! Logs count:", len(trace_data.get("logs", [])))
            print("Severity:", trace_data.get("severity"))
            print("Report Summary:\n", trace_data.get("report")[:200] + "...")
            return
        time.sleep(1.0)
    raise TimeoutError("Agent trace took too long to generate")

def test_agent_chat():
    print("Testing Agent Chat Endpoint...")
    payload = {
        "message": "What is the severity of the active flood near Muzaffarpur?",
        "lastResult": {
            "location": "Muzaffarpur",
            "area_sq_km": 3.5,
            "severity": "HIGH",
            "impact": {
                "population": 4200,
                "buildings": 150,
                "facilities": 2
            }
        }
    }
    res = requests.post(f"{BASE_URL}/api/agent/chat", json=payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert "response" in data, "Missing response field in chat"
    print("✓ Agent Chat Response:")
    print(data["response"])

if __name__ == "__main__":
    print("STARTING API ENDPOINT VERIFICATION")
    try:
        test_root()
        print("-" * 40)
        test_preview()
        print("-" * 40)
        test_detection_pipeline()
        print("-" * 40)
        test_crowd_report()
        print("-" * 40)
        test_complaints_list()
        print("-" * 40)
        test_agent_cycle()
        print("-" * 40)
        test_agent_chat()
        print("-" * 40)
        print("ALL API ENDPOINTS TESTED AND FUNCTIONAL!")
    except AssertionError as e:
        print(f"API FAILURE: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"API ERROR: {e}")
        sys.exit(1)
