# Copyright 2026 Muhammad Waleed & Areeba
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time
import httpx

CORE_ENGINE_URL = "http://localhost:8000"

def run_integration_test():
    print("====================================================")
    print(" Taafi.ai - Deadlock Autopilot Healing Integration Test")
    print("====================================================")
    
    print("\n1. Verifying Core Engine Connectivity...")
    try:
        res = httpx.get(f"{CORE_ENGINE_URL}/health")
        if res.status_code == 200:
            print("[SUCCESS] Core Engine is online and healthy!")
        else:
            print(f"[FAIL] Core Engine returned status code {res.status_code}")
            return
    except Exception as e:
        print(f"[FAIL] Core Engine offline. Make sure 'uvicorn main:app' is running on port 8000. Error: {e}")
        return

    print("\n2. Triggering Deadlock Simulation Scenario...")
    try:
        res = httpx.post(f"{CORE_ENGINE_URL}/api/incidents/simulate")
        if res.status_code == 200:
            incident_id = res.json()["incident_id"]
            print(f"[SUCCESS] Trapped simulated deadlock: {incident_id}")
        else:
            print(f"[FAIL] Could not simulate deadlock: {res.text}")
            return
    except Exception as e:
        print(f"[FAIL] Deadlock simulation trigger failed: {e}")
        return

    print("\n3. Waiting for Autopilot Self-Healing Loop...")
    max_wait = 10
    healed = False
    
    for i in range(1, max_wait + 1):
        print(f"Polling active incidents (Attempt {i}/{max_wait})...")
        time.sleep(1.0)
        
        try:
            res = httpx.get(f"{CORE_ENGINE_URL}/api/incidents")
            if res.status_code == 200:
                incidents = res.json()
                # Find if our simulated incident has been remediated
                matching = [inc for inc in incidents if inc.get("details", {}).get("incident_id") == incident_id]
                
                # Check if there is a REMEDIATION_COMPLETED log with our incident_id
                resolved = any(
                    inc.get("category") == "REMEDIATION_COMPLETED" and inc.get("details", {}).get("incident_id") == incident_id
                    for inc in incidents
                )
                
                if resolved:
                    print(f"\n[SUCCESS] Autopilot Agent fully healed database incident {incident_id}!")
                    print(f"Remediation SQL hot-patched successfully!")
                    healed = True
                    break
        except Exception as e:
            print(f"Error polling incidents: {e}")
            break

    if not healed:
        print(f"\n[FAIL] Autopilot self-healing loop timed out. Make sure 'python orchestrator.py' is running.")
    print("====================================================")

if __name__ == "__main__":
    run_integration_test()
