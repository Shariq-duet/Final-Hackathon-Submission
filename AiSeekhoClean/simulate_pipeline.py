import requests
import json
import logging
import sys

# Configure basic logging to ensure telemetry is captured for Mission Control
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("MissionControl")

def main():
    analyze_url = "https://community-ai-backend-631639319596.us-central1.run.app/analyze-local"
    execute_url = "https://community-ai-backend-631639319596.us-central1.run.app/execute"

    logger.info("Starting end-to-end pipeline simulation.")
    
    # Step 1: Trigger Analysis
    logger.info(f"Agent Action: Triggering HTTP POST request to cloud endpoint for analysis...")
    logger.info(f"Target URL: {analyze_url}")
    
    try:
        # Note: analyze-local does not expect a payload based on the server.py implementation,
        # but if we were using the exact antigravity_skill.py function, it passes a payload.
        # We will just send an empty POST request here.
        response_analyze = requests.post(analyze_url, timeout=600)
        response_analyze.raise_for_status()
        
        plan_json = response_analyze.json()
        logger.info("Agent Observation: Successfully retrieved execution plan from cloud.")
        
        # Log a snippet of the plan for telemetry
        plan_snippet = json.dumps(plan_json, indent=2)[:500]
        logger.info(f"Execution Plan Preview:\n{plan_snippet}\n... [truncated]")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Agent Error during Phase 1/2: HTTP request failed. Details: {e}")
        if hasattr(e, 'response') and e.response is not None:
             logger.error(f"Response Body: {e.response.text}")
        sys.exit(1)

    # Step 2: Simulate Human Approval and Execute
    logger.info("Agent Action: Simulating human approval. Forwarding plan to execution endpoint...")
    logger.info(f"Target URL: {execute_url}")
    
    headers = {"Content-Type": "application/json"}
    try:
        response_execute = requests.post(execute_url, json=plan_json, headers=headers, timeout=120)
        response_execute.raise_for_status()
        
        execute_result = response_execute.json()
        logger.info(f"Agent Observation: Execution successful. Status Code: {response_execute.status_code}")
        logger.info(f"Final Server Response:\n{json.dumps(execute_result, indent=2)}")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Agent Error during Phase 3: Execution failed. Details: {e}")
        if hasattr(e, 'response') and e.response is not None:
             logger.error(f"Response Body: {e.response.text}")
        sys.exit(1)

if __name__ == "__main__":
    main()
