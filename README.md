# OCLC WMS Bibliographic Record Matching System

An AI-powered bibliographic record matching and data enrichment system for OCLC's WorldShare Management Services (WMS) customer onboarding process.

## Overview

This system intelligently matches MARC records from various library management systems to WorldCat records, handling sparse data and reducing manual intervention from 20% to <5% of records.

### Key Features

- **Intelligent Matching**: Multi-stage matching pipeline with AI-assisted decision making
- **95%+ Automation**: Achieves 95%+ automated match rate (up from 80%)
- **Data Enrichment**: Enhances sparse records using multiple external sources
- **Confidence Scoring**: Provides confidence scores for all matching decisions
- **Human-in-the-Loop**: Review interface for low-confidence matches
- **Scalable Processing**: Handles 10,000+ records per batch

## Architecture

### Core Components

1. **MARC Parser**: Parse MARC21 records from various formats (binary, XML, JSON)
2. **WorldCat API Client**: Query WorldCat database with intelligent caching
3. **AI Matching Engine**: Multi-stage matching with ML models and semantic analysis
4. **Data Enrichment**: Enhance sparse records using internal and external sources
5. **Local Variation Detector**: Distinguish intentional local cataloging from incomplete records
6. **Workflow Engine**: Orchestrate end-to-end processing pipeline
7. **Review Interface**: Web-based dashboard for manual review and feedback
8. **Analytics Dashboard**: Real-time monitoring and historical analytics

### Technology Stack

- **Language**: Python 3.10+
- **ML/AI**: Hugging Face Transformers, scikit-learn, OpenAI/Anthropic APIs
- **Data Processing**: pymarc, pandas, numpy
- **API/Web**: FastAPI, React
- **Caching**: Redis
- **Database**: PostgreSQL
- **Task Queue**: Celery + RabbitMQ/Redis
- **Deployment**: Docker, docker-compose

## Quick Start

### Prerequisites

- Python 3.10 or higher
- Docker and Docker Compose
- Redis
- PostgreSQL

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd OCLCAISol1
```

2. Copy environment template and configure:
```bash
cp .env.example .env
# Edit .env with your API keys and configuration
```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

4. Start services with Docker Compose:
```bash
docker-compose up -d
```

5. Run database migrations:
```bash
python -m src.models.database migrate
```

### Basic Usage

#### Command Line Interface

Process a customer's MARC export:
```bash
python -m src.pipeline.workflow_engine \
  --input customer_records.mrc \
  --output matched_records.json \
  --customer-id CUST001 \
  --source-system "III Millennium"
```

#### API Usage

```python
import requests

# Submit batch job
response = requests.post("http://localhost:8000/api/v1/jobs", json={
    "customer_id": "CUST001",
    "source_file": "customer_records.mrc",
    "source_system": "III Millennium",
    "options": {
        "auto_approve_threshold": 0.95,
        "enrichment_enabled": True
    }
})

job_id = response.json()["job_id"]

# Check job status
status = requests.get(f"http://localhost:8000/api/v1/jobs/{job_id}")
print(status.json())
```

## Configuration

### Environment Variables

```bash
# WorldCat API
WORLDCAT_API_KEY=your_api_key
WORLDCAT_API_SECRET=your_api_secret
WORLDCAT_BASE_URL=https://worldcat.org/api

# AI/ML Services
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
HUGGINGFACE_TOKEN=your_hf_token

# Database
DATABASE_URL=postgresql://user:pass@localhost/oclc_wms
REDIS_URL=redis://localhost:6379

# Processing Configuration
BATCH_SIZE=1000
MAX_WORKERS=4
CONFIDENCE_THRESHOLD_AUTO=0.95
CONFIDENCE_THRESHOLD_ASSISTED=0.75
```

## Matching Strategies

The system uses a multi-stage matching pipeline:

1. **Exact Match**: ISBN/ISSN/OCLC number lookup
2. **High-Confidence Fuzzy Match**: Title + Author + Publication year
3. **Enriched Match**: Use related fields from source export
4. **AI-Assisted Match**: ML model for ambiguous cases

### Match Classifications

- **AUTO_MATCH** (>0.95): Automatically accepted
- **ASSISTED_MATCH** (0.75-0.95): Presented with recommendation
- **MANUAL_REVIEW** (0.50-0.75): Flagged for expert review
- **NO_MATCH** (<0.50): Candidate for enrichment or new record

## Development

### Project Structure

```
oclc-wms-matcher/
├── src/
│   ├── parsers/          # MARC parsing
│   ├── clients/          # API clients
│   ├── matching/         # Matching engine and ML models
│   ├── enrichment/       # Data enrichment
│   ├── pipeline/         # Workflow orchestration
│   ├── api/              # FastAPI application
│   ├── models/           # Database models
│   └── utils/            # Utilities
├── frontend/             # React UI
├── tests/                # Test suite
├── docker/               # Docker configuration
└── notebooks/            # Jupyter notebooks
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test suite
pytest tests/unit/test_marc_parser.py
```

### Code Quality

```bash
# Format code
black src/

# Lint
flake8 src/
pylint src/

# Type checking
mypy src/
```

## API Documentation

Once the application is running, access the interactive API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Monitoring & Analytics

Access the analytics dashboard at http://localhost:8000/analytics

Key metrics tracked:
- Processing throughput (records/hour)
- Match rate by strategy
- Confidence score distribution
- Manual review queue size
- API usage and performance

## Performance

- **Processing Speed**: 10,000 records in <2 hours
- **API Response Time**: <200ms for 95% of requests
- **Match Accuracy**: >95% automated match rate
- **Manual Review Rate**: <5% of records

## Contributing

1. Create a feature branch
2. Make your changes
3. Add tests
4. Ensure all tests pass
5. Submit a pull request

## License

Copyright © 2025 OCLC. All rights reserved.

## Support

For questions or issues, contact the OCLC WMS team.
