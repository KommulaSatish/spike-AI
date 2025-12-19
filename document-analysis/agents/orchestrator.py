"""
Orchestrator - Central decision-making layer
Handles intent detection, agent routing, and response aggregation
"""

import json
import logging
import re
from typing import Any, Optional

from agents.analytics_agent import AnalyticsAgent
from agents.seo_agent import SEOAgent
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Central orchestrator for multi-agent system.
    Responsibilities:
    - Intent detection
    - Agent routing
    - Task decomposition
    - Response aggregation
    """
    
    def __init__(self):
        self.llm_client = LLMClient()
        self.analytics_agent: Optional[AnalyticsAgent] = None
        self.seo_agent: Optional[SEOAgent] = None
        
    async def initialize(self):
        """Initialize all agents"""
        logger.info("Initializing agents...")
        
        # Initialize Analytics Agent
        self.analytics_agent = AnalyticsAgent(self.llm_client)
        await self.analytics_agent.initialize()
        
        # Initialize SEO Agent
        self.seo_agent = SEOAgent(self.llm_client)
        await self.seo_agent.initialize()
        
        logger.info("All agents initialized successfully")
    
    async def detect_intent(self, query: str) -> dict:
        """
        Detect the intent of the query and determine which agents to use.
        Returns routing information.
        """
        prompt = f"""Analyze this query and determine which agents should handle it.

Query: "{query}"

Available agents:
1. ANALYTICS - For GA4/Google Analytics queries (page views, sessions, users, traffic sources, etc.)
2. SEO - For SEO audit queries (URLs, title tags, meta descriptions, indexability, HTTPS status, etc.)
3. BOTH - For queries requiring data from both analytics AND SEO

Return a JSON object with:
{{
    "primary_intent": "ANALYTICS" | "SEO" | "BOTH",
    "requires_analytics": true/false,
    "requires_seo": true/false,
    "analytics_subtask": "description of analytics task if needed",
    "seo_subtask": "description of SEO task if needed",
    "fusion_required": true/false,
    "output_format": "natural_language" | "json",
    "confidence": 0.0-1.0
}}

Indicators for ANALYTICS:
- Mentions: page views, sessions, users, traffic, visitors, engagement, bounce rate, conversions
- Time-based analysis: last N days, trends, daily breakdown
- Traffic sources, devices, countries, referrals

Indicators for SEO:
- Mentions: URLs, title tags, meta descriptions, indexability, HTTPS, crawl data
- Screaming Frog data references
- Technical SEO terms

Indicators for BOTH:
- Combines traffic data with SEO attributes
- "Top pages by views AND their title tags"
- Cross-referencing analytics with SEO data

Return ONLY the JSON object, no other text."""

        response = await self.llm_client.generate(prompt, temperature=0.1)
        
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                intent = json.loads(json_match.group())
                logger.info(f"Detected intent: {intent['primary_intent']} (confidence: {intent.get('confidence', 'N/A')})")
                return intent
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse intent JSON: {e}")
        
        # Default fallback based on keywords
        query_lower = query.lower()
        
        analytics_keywords = ['page view', 'session', 'user', 'traffic', 'visitor', 'engagement', 
                            'bounce', 'conversion', 'source', 'medium', 'daily', 'weekly', 'trend']
        seo_keywords = ['url', 'title tag', 'meta description', 'indexab', 'https', 'crawl', 
                       'screaming frog', 'seo', 'canonical', 'robots']
        
        has_analytics = any(kw in query_lower for kw in analytics_keywords)
        has_seo = any(kw in query_lower for kw in seo_keywords)
        
        if has_analytics and has_seo:
            return {
                "primary_intent": "BOTH",
                "requires_analytics": True,
                "requires_seo": True,
                "fusion_required": True,
                "output_format": "json" if "json" in query_lower else "natural_language",
                "confidence": 0.7
            }
        elif has_seo:
            return {
                "primary_intent": "SEO",
                "requires_analytics": False,
                "requires_seo": True,
                "fusion_required": False,
                "output_format": "json" if "json" in query_lower else "natural_language",
                "confidence": 0.7
            }
        else:
            return {
                "primary_intent": "ANALYTICS",
                "requires_analytics": True,
                "requires_seo": False,
                "fusion_required": False,
                "output_format": "json" if "json" in query_lower else "natural_language",
                "confidence": 0.7
            }
    
    async def process(self, query: str, property_id: Optional[str] = None) -> dict:
        """
        Main processing pipeline.
        """
        # Step 1: Detect intent
        intent = await self.detect_intent(query)
        
        agents_used = []
        results = {}
        
        # Step 2: Route to appropriate agents
        if intent.get("requires_analytics", False):
            if not property_id:
                raise ValueError("propertyId is required for analytics queries")
            
            logger.info("Routing to Analytics Agent...")
            analytics_result = await self.analytics_agent.process(
                query=intent.get("analytics_subtask", query),
                property_id=property_id,
                full_query=query
            )
            results["analytics"] = analytics_result
            agents_used.append("analytics")
        
        if intent.get("requires_seo", False):
            logger.info("Routing to SEO Agent...")
            seo_result = await self.seo_agent.process(
                query=intent.get("seo_subtask", query),
                full_query=query
            )
            results["seo"] = seo_result
            agents_used.append("seo")
        
        # Step 3: Aggregate results
        if intent.get("fusion_required", False) and len(results) > 1:
            logger.info("Performing cross-agent data fusion...")
            final_result = await self._fuse_results(query, results, intent)
        elif "analytics" in results:
            final_result = results["analytics"]
        elif "seo" in results:
            final_result = results["seo"]
        else:
            final_result = {
                "answer": "I couldn't determine which agent should handle this query.",
                "data": None
            }
        
        final_result["agents_used"] = agents_used
        return final_result
    
    async def _fuse_results(self, query: str, results: dict, intent: dict) -> dict:
        """
        Fuse results from multiple agents into a unified response.
        """
        analytics_data = results.get("analytics", {})
        seo_data = results.get("seo", {})
        
        # Check if we need to match pages from analytics with SEO data
        analytics_pages = analytics_data.get("data", {}).get("pages", [])
        seo_pages = seo_data.get("data", {}).get("urls", [])
        
        # Create fusion prompt
        prompt = f"""You are a data fusion expert. Combine the following data from two sources to answer the user's question.

User Question: "{query}"

ANALYTICS DATA (from GA4):
{json.dumps(analytics_data.get('data', {}), indent=2)}

SEO DATA (from Screaming Frog):
{json.dumps(seo_data.get('data', {}), indent=2)}

Instructions:
1. Match pages from analytics with their corresponding SEO data by URL/page path
2. Combine the relevant information
3. Answer the user's question comprehensively
4. If the user requested JSON format, return structured JSON
5. Highlight any insights from combining both data sources

{"Return the answer as a valid JSON object." if intent.get('output_format') == 'json' else "Provide a clear natural language explanation."}"""

        response = await self.llm_client.generate(prompt, temperature=0.3)
        
        # Try to parse as JSON if requested
        if intent.get('output_format') == 'json':
            try:
                json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
                if json_match:
                    data = json.loads(json_match.group(1))
                    return {
                        "answer": response,
                        "data": data,
                        "reasoning": "Cross-agent fusion performed successfully"
                    }
                else:
                    json_match = re.search(r'\[[\s\S]*\]|\{[\s\S]*\}', response)
                    if json_match:
                        data = json.loads(json_match.group())
                        return {
                            "answer": response,
                            "data": data,
                            "reasoning": "Cross-agent fusion performed successfully"
                        }
            except json.JSONDecodeError:
                pass
        
        return {
            "answer": response,
            "data": {
                "analytics": analytics_data.get("data"),
                "seo": seo_data.get("data")
            },
            "reasoning": "Cross-agent fusion performed successfully"
        }
