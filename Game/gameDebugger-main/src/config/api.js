const BASE_URL = "https://community-ai-backend-631639319596.us-central1.run.app";
export const EXECUTE_URL = `${BASE_URL}/execute`;
export const ANALYZE_LOCAL_URL = `${BASE_URL}/analyze-local`;
export const ANALYZE_DEMO_URL = `${BASE_URL}/analyze-demo`;
export const ANALYZE_DISCORD_URL = `${BASE_URL}/analyze-discord`;
export const STREAM_URL = (jobId) => `${BASE_URL}/stream/${jobId}`;
export const RESULT_URL = (jobId) => `${BASE_URL}/result/${jobId}`;
export const HEALTH_URL = `${BASE_URL}/health`;