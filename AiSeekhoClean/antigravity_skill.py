import requests
import json
import logging

# Configure basic logging to ensure telemetry is captured
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("AntigravityAgentManager")

def trigger_cloud_analysis(payload: dict) -> dict:
    """
    Sends an HTTP POST request to the live cloud endpoint to analyze local data.
    
    Args:
        payload (dict): The data payload to send for analysis.
        
    Returns:
        dict: The massive JSON execution plan returned by the cloud server.
    """
    url = "https://community-ai-backend-631639319596.us-central1.run.app/analyze-local"
    try:
        logger.info("Agent Action: Triggering HTTP POST request to cloud endpoint...")
        logger.info(f"Target URL: {url}")
        
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        
        logger.info("Agent Observation: Successfully retrieved execution plan from cloud.")
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Agent Error: HTTP request failed. Details: {e}")
        return {"error": str(e)}
