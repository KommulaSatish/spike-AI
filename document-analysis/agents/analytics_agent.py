"""
Analytics Agent - GA4 Data API Integration
Handles natural language queries for Google Analytics data
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Filter,
    FilterExpression,
    FilterExpressionList,
    Metric,
    OrderBy,
    RunReportRequest,
)
from google.oauth2 import service_account

from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


# Valid GA4 metrics and dimensions (allowlist for validation)
VALID_METRICS = {
    "activeUsers", "newUsers", "totalUsers", "sessions", "sessionsPerUser",
    "screenPageViews", "screenPageViewsPerSession", "screenPageViewsPerUser",
    "engagedSessions", "engagementRate", "averageSessionDuration",
    "bounceRate", "eventCount", "eventsPerSession", "conversions",
    "totalRevenue", "transactions", "purchaseRevenue", "userEngagementDuration",
    "dauPerMau", "dauPerWau", "wauPerMau", "crashFreeUsersRate",
    "scrolledUsers", "sessionConversionRate", "userConversionRate"
}

VALID_DIMENSIONS = {
    "date", "dateHour", "dateHourMinute", "day", "dayOfWeek", "dayOfWeekName",
    "firstSessionDate", "hour", "month", "nthDay", "nthHour", "nthMonth", 
    "nthWeek", "nthYear", "week", "year", "yearMonth", "yearWeek",
    "city", "cityId", "country", "countryId", "continent", "continentId",
    "region", "subContinent", "deviceCategory", "deviceModel", "mobileDeviceBranding",
    "mobileDeviceMarketingName", "mobileDeviceModel", "operatingSystem",
    "operatingSystemVersion", "operatingSystemWithVersion", "platform",
    "browser", "browserVersion", "language", "screenResolution",
    "pagePath", "pagePathPlusQueryString", "pageTitle", "landingPage",
    "landingPagePlusQueryString", "exitPage", "hostname", "unifiedPageScreen",
    "sessionSource", "sessionMedium", "sessionSourceMedium", "sessionCampaignName",
    "sessionDefaultChannelGroup", "firstUserSource", "firstUserMedium",
    "firstUserSourceMedium", "firstUserCampaignName", "newVsReturning",
    "eventName", "isConversionEvent", "transactionId", "itemId", "itemName",
    "itemBrand", "itemCategory", "itemCategory2", "itemCategory3", "itemCategory4",
    "itemCategory5", "itemListName", "itemPromotionName"
}


class AnalyticsAgent:
    """
    Analytics Agent for GA4 Data API.
    Translates natural language queries to GA4 API requests.
    """
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.ga_client: Optional[BetaAnalyticsDataClient] = None
        
    async def initialize(self):
        """Initialize GA4 client with credentials"""
        try:
            credentials_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "credentials.json")
            
            if not os.path.exists(credentials_path):
                logger.warning(f"credentials.json not found at {credentials_path}")
                return
            
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=["https://www.googleapis.com/auth/analytics.readonly"]
            )
            
            self.ga_client = BetaAnalyticsDataClient(credentials=credentials)
            logger.info("✅ GA4 client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize GA4 client: {e}")
            raise
    
    async def _parse_query_to_ga4_plan(self, query: str) -> dict:
        """
        Use LLM to translate natural language query to GA4 reporting plan.
        """
        prompt = f"""You are a Google Analytics 4 expert. Parse this natural language query into a GA4 reporting plan.

Query: "{query}"

Available metrics (use exact names):
{', '.join(sorted(VALID_METRICS))}

Available dimensions (use exact names):
{', '.join(sorted(VALID_DIMENSIONS))}

Return a JSON object with:
{{
    "metrics": ["metric1", "metric2"],  // List of metric names
    "dimensions": ["dimension1"],  // List of dimension names  
    "date_range": {{
        "start_date": "YYYY-MM-DD or relative like '30daysAgo'",
        "end_date": "YYYY-MM-DD or relative like 'yesterday'"
    }},
    "filters": [
        {{
            "dimension": "dimension_name",
            "operator": "EXACT" | "CONTAINS" | "BEGINS_WITH" | "ENDS_WITH" | "REGEXP",
            "value": "filter_value"
        }}
    ],
    "order_by": {{
        "field": "metric or dimension name",
        "descending": true/false
    }},
    "limit": 10,  // Number of rows to return
    "comparison_period": null | {{  // For comparison queries
        "start_date": "YYYY-MM-DD",
        "end_date": "YYYY-MM-DD"
    }}
}}

Guidelines:
- For "page views" use "screenPageViews"
- For "users" use "activeUsers" or "totalUsers"
- For "sessions" use "sessions"
- For "traffic sources" use dimension "sessionSourceMedium" or "sessionDefaultChannelGroup"
- For daily breakdown use dimension "date"
- For page-specific queries, use "pagePath" dimension with filter
- "last 7 days" = start_date: "7daysAgo", end_date: "yesterday"
- "last 14 days" = start_date: "14daysAgo", end_date: "yesterday"
- "last 30 days" = start_date: "30daysAgo", end_date: "yesterday"
- For /pricing page, filter pagePath CONTAINS "/pricing"
- For homepage, filter pagePath EXACT "/"

Return ONLY the JSON object."""

        response = await self.llm_client.generate(prompt, temperature=0.1)
        
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                plan = json.loads(json_match.group())
                
                # Validate metrics
                plan["metrics"] = [m for m in plan.get("metrics", []) if m in VALID_METRICS]
                if not plan["metrics"]:
                    plan["metrics"] = ["screenPageViews", "activeUsers", "sessions"]
                
                # Validate dimensions
                plan["dimensions"] = [d for d in plan.get("dimensions", []) if d in VALID_DIMENSIONS]
                
                logger.info(f"Generated GA4 plan: metrics={plan['metrics']}, dimensions={plan['dimensions']}")
                return plan
                
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse GA4 plan: {e}")
        
        # Default fallback plan
        return {
            "metrics": ["screenPageViews", "activeUsers", "sessions"],
            "dimensions": ["date"],
            "date_range": {"start_date": "14daysAgo", "end_date": "yesterday"},
            "filters": [],
            "limit": 100
        }
    
    async def _execute_ga4_query(self, property_id: str, plan: dict) -> dict:
        """
        Execute GA4 Data API query based on the plan.
        """
        if not self.ga_client:
            raise ValueError("GA4 client not initialized. Check credentials.json")
        
        # Build metrics
        metrics = [Metric(name=m) for m in plan.get("metrics", [])]
        
        # Build dimensions
        dimensions = [Dimension(name=d) for d in plan.get("dimensions", [])]
        
        # Build date range
        date_range = plan.get("date_range", {})
        date_ranges = [
            DateRange(
                start_date=date_range.get("start_date", "14daysAgo"),
                end_date=date_range.get("end_date", "yesterday")
            )
        ]
        
        # Add comparison period if specified
        if plan.get("comparison_period"):
            comp = plan["comparison_period"]
            date_ranges.append(
                DateRange(
                    start_date=comp["start_date"],
                    end_date=comp["end_date"]
                )
            )
        
        # Build filters
        dimension_filter = None
        filters = plan.get("filters", [])
        if filters:
            filter_expressions = []
            for f in filters:
                if f.get("dimension") in VALID_DIMENSIONS:
                    string_filter = Filter.StringFilter(
                        match_type=getattr(Filter.StringFilter.MatchType, f.get("operator", "CONTAINS")),
                        value=f.get("value", "")
                    )
                    filter_expressions.append(
                        FilterExpression(
                            filter=Filter(
                                field_name=f["dimension"],
                                string_filter=string_filter
                            )
                        )
                    )
            
            if len(filter_expressions) == 1:
                dimension_filter = filter_expressions[0]
            elif len(filter_expressions) > 1:
                dimension_filter = FilterExpression(
                    and_group=FilterExpressionList(expressions=filter_expressions)
                )
        
        # Build order by
        order_bys = []
        if plan.get("order_by"):
            order_by = plan["order_by"]
            field = order_by.get("field", "")
            if field in VALID_METRICS:
                order_bys.append(
                    OrderBy(
                        metric=OrderBy.MetricOrderBy(metric_name=field),
                        desc=order_by.get("descending", True)
                    )
                )
            elif field in VALID_DIMENSIONS:
                order_bys.append(
                    OrderBy(
                        dimension=OrderBy.DimensionOrderBy(dimension_name=field),
                        desc=order_by.get("descending", True)
                    )
                )
        
        # Build request
        request = RunReportRequest(
            property=f"properties/{property_id}",
            metrics=metrics,
            dimensions=dimensions if dimensions else None,
            date_ranges=date_ranges,
            dimension_filter=dimension_filter,
            order_bys=order_bys if order_bys else None,
            limit=plan.get("limit", 100)
        )
        
        logger.info(f"Executing GA4 query for property {property_id}")
        
        try:
            response = self.ga_client.run_report(request)
            
            # Parse response
            result = {
                "row_count": response.row_count,
                "metrics": [m.name for m in response.metric_headers],
                "dimensions": [d.name for d in response.dimension_headers],
                "rows": []
            }
            
            for row in response.rows:
                row_data = {}
                
                for i, dim in enumerate(response.dimension_headers):
                    row_data[dim.name] = row.dimension_values[i].value
                
                for i, metric in enumerate(response.metric_headers):
                    row_data[metric.name] = row.metric_values[i].value
                
                result["rows"].append(row_data)
            
            logger.info(f"GA4 query returned {result['row_count']} rows")
            return result
            
        except Exception as e:
            logger.error(f"GA4 query failed: {e}")
            raise
    
    async def _generate_analysis(self, query: str, data: dict, plan: dict) -> str:
        """
        Generate natural language analysis of the GA4 data.
        """
        # Check if data is empty
        if not data.get("rows"):
            return f"""Based on the GA4 data query, no data was returned for the specified criteria.

This could mean:
1. The property has no traffic data for the specified date range ({plan.get('date_range', {}).get('start_date', 'N/A')} to {plan.get('date_range', {}).get('end_date', 'N/A')})
2. The specified filters (e.g., page path) don't match any recorded data
3. The property is new and hasn't collected sufficient data yet

The query was executed successfully, but returned zero results. This is a valid outcome for properties with little or no traffic."""
        
        # Prepare data summary for LLM
        data_summary = json.dumps(data["rows"][:50], indent=2)  # Limit to 50 rows for context
        
        prompt = f"""Analyze this Google Analytics data and provide insights for the user's question.

User Question: "{query}"

Query Parameters:
- Metrics: {plan.get('metrics', [])}
- Dimensions: {plan.get('dimensions', [])}
- Date Range: {plan.get('date_range', {})}
- Filters: {plan.get('filters', [])}

Data (up to 50 rows):
{data_summary}

Total rows returned: {data.get('row_count', 0)}

Provide a clear, insightful analysis that:
1. Directly answers the user's question
2. Highlights key trends and patterns
3. Includes specific numbers from the data
4. Provides actionable insights when relevant
5. Notes any limitations or caveats

Be concise but thorough."""

        response = await self.llm_client.generate(prompt, temperature=0.3)
        return response
    
    async def process(self, query: str, property_id: str, full_query: Optional[str] = None) -> dict:
        """
        Main processing method for analytics queries.
        """
        try:
            # Step 1: Parse query to GA4 plan
            plan = await self._parse_query_to_ga4_plan(full_query or query)
            
            # Step 2: Execute GA4 query
            data = await self._execute_ga4_query(property_id, plan)
            
            # Step 3: Generate analysis
            analysis = await self._generate_analysis(full_query or query, data, plan)
            
            return {
                "answer": analysis,
                "data": {
                    "query_plan": plan,
                    "pages": data.get("rows", []),
                    "row_count": data.get("row_count", 0),
                    "metrics": data.get("metrics", []),
                    "dimensions": data.get("dimensions", [])
                },
                "reasoning": f"Queried GA4 with metrics {plan['metrics']} and dimensions {plan.get('dimensions', [])}"
            }
            
        except Exception as e:
            logger.error(f"Analytics agent error: {e}", exc_info=True)
            return {
                "answer": f"Error processing analytics query: {str(e)}",
                "data": None,
                "reasoning": f"Failed to execute GA4 query: {str(e)}"
            }
