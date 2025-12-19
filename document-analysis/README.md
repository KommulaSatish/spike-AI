# Spike AI Multi-Agent System

A production-ready AI backend for answering natural-language questions about Web Analytics (GA4) and SEO Audits (Screaming Frog exports).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      API Layer (FastAPI)                     │
│                    POST /query (port 8080)                   │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                       Orchestrator                           │
│  • Intent Detection (LLM-powered)                           │
│  • Agent Routing                                            │
│  • Task Decomposition                                       │
│  • Response Aggregation & Fusion                            │
└───────────┬─────────────────────────────────┬───────────────┘
            │                                 │
            ▼                                 ▼
┌───────────────────────┐       ┌───────────────────────────┐
│   Analytics Agent     │       │       SEO Agent           │
│   (Tier 1 - GA4)      │       │   (Tier 2 - Screaming     │
│                       │       │         Frog)             │
│ • NL → GA4 Query      │       │ • Google Sheets Live      │
│ • Metrics/Dimensions  │       │ • Filtering/Aggregation   │
│ • Date Range Parsing  │       │ • Schema-Safe Queries     │
│ • Server Validation   │       │                           │
└───────────┬───────────┘       └───────────┬───────────────┘
            │                                 │
            ▼                                 ▼
┌───────────────────────┐       ┌───────────────────────────┐
│  Google Analytics     │       │     Google Sheets API     │
│    Data API (GA4)     │       │   (Screaming Frog Data)   │
└───────────────────────┘       └───────────────────────────┘
```

## Features

### Tier 1 - Analytics Agent
- Natural language to GA4 query translation
- Server-side metric/dimension validation against allowlist
- Flexible date range parsing ("last 14 days", "previous month", etc.)
- Property-agnostic design (works with any GA4 property)
- Graceful handling of empty/sparse datasets
- Clear natural language explanations with data insights

### Tier 2 - SEO Agent
- Live Google Sheets data ingestion
- Complex filtering with multiple operators
- Grouping and aggregation support
- Percentage calculations for SEO health metrics
- Schema-safe operations (handles column changes)

### Tier 3 - Multi-Agent System
- Automatic intent detection using LLM
- Cross-agent data fusion for combined queries
- Unified response generation
- Supports JSON output format when requested

## Setup Instructions

### Prerequisites
- Python 3.10+
- Google Cloud project with GA4 Data API enabled
- Google Analytics account with GA4 property
- LiteLLM API key

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd spike-ai-agent
```

2. Set up credentials:
   - Place your `credentials.json` file at the project root
   - The file should contain Google Cloud service account credentials
   - Ensure the service account has access to:
     - Google Analytics Data API
     - Google Sheets API (read-only)

3. Set environment variables:
```bash
export LITELLM_API_KEY="sk-your-key-here"
```

4. Run the deployment script:
```bash
bash deploy.sh
```

### API Usage

**Endpoint:** `POST http://localhost:8080/query`

**Analytics Query (Tier 1):**
```json
{
  "propertyId": "123456789",
  "query": "Give me a daily breakdown of page views, users, and sessions for the /pricing page over the last 14 days."
}
```

**SEO Query (Tier 2):**
```json
{
  "query": "Which URLs do not use HTTPS and have title tags longer than 60 characters?"
}
```

**Multi-Agent Query (Tier 3):**
```json
{
  "propertyId": "123456789",
  "query": "What are the top 10 pages by page views in the last 14 days, and what are their corresponding title tags?"
}
```

## Data Source Integrations

### Google Analytics 4
- Uses GA4 Data API v1beta
- Credentials loaded from `credentials.json` at runtime
- Property ID provided per request (evaluator-safe)

### Screaming Frog (Google Sheets)
- Sheet URL: [Screaming Frog Data](https://docs.google.com/spreadsheets/d/1zzf4ax_H2WiTBVrJigGjF2Q3Yz-qy2qMCbAMKvl6VEE)
- Live data access (refreshed on each query)
- Supports all standard Screaming Frog export columns

## Assumptions and Limitations

### Assumptions
1. `credentials.json` will be replaced by evaluators during evaluation
2. GA4 property may have zero traffic (handled gracefully)
3. LiteLLM API key will be valid and within budget
4. Screaming Frog data follows standard export format

### Limitations
1. GA4 queries limited to supported metrics/dimensions in allowlist
2. SEO data cached per session (manual refresh available)
3. Complex multi-step analytical queries may require multiple calls
4. Rate limiting handled with exponential backoff (may cause delays)

## Project Structure

```
├── main.py                 # FastAPI application entry point
├── deploy.sh               # Deployment script
├── requirements.txt        # Python dependencies
├── credentials.json        # Google API credentials (not in repo)
├── README.md               # This file
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py     # Central routing and fusion logic
│   ├── analytics_agent.py  # GA4 Data API integration
│   └── seo_agent.py        # Google Sheets integration
└── utils/
    ├── __init__.py
    ├── llm_client.py       # LiteLLM client with retry logic
    └── logger.py           # Logging configuration
```

## Error Handling

- Invalid GA4 metrics/dimensions are filtered against allowlist
- Missing `propertyId` returns clear validation error
- Empty datasets return informative messages
- API rate limits handled with exponential backoff
- All errors logged with full stack traces

## Testing

Run the test suite:
```bash
python -m pytest tests/ -v
```

## License

MIT License
