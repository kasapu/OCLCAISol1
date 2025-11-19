# OCLC WMS Matcher - Quick Start Guide

Get the system running in 5 minutes!

## Prerequisites

- Docker Desktop installed and running
- Git installed
- Text editor

## Step 1: Get the Code (30 seconds)

```bash
git clone <repository-url>
cd OCLCAISol1
```

## Step 2: Configure Environment (1 minute)

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your API keys (minimum required):
nano .env
```

**Minimum Configuration**:
```bash
# WorldCat API (required for matching)
WORLDCAT_API_KEY=your_key_here
WORLDCAT_API_SECRET=your_secret_here

# AI Services (optional - enables enrichment)
OPENAI_API_KEY=your_openai_key_here
# OR
ANTHROPIC_API_KEY=your_anthropic_key_here
```

**Note**: The system will work without AI API keys, but enrichment features will be disabled.

## Step 3: Start the System (2 minutes)

```bash
# Start all services with Docker Compose
docker-compose up -d

# Wait for services to initialize (~30 seconds)
# Watch the logs
docker-compose logs -f api
```

You should see:
```
api_1       | INFO:     Started server process
api_1       | INFO:     Uvicorn running on http://0.0.0.0:8000
```

## Step 4: Verify It's Working (30 seconds)

**Test the API**:
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-19T..."
}
```

**Open API Documentation**:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Step 5: Try Matching a Record (1 minute)

### Option A: Using the API Docs

1. Open http://localhost:8000/docs
2. Find `POST /api/v1/match/single`
3. Click "Try it out"
4. Upload a MARC file (.mrc format)
5. Click "Execute"

### Option B: Using Python

Create `test_match.py`:
```python
from src.parsers.marc_parser import MARCParser, MARCRecord
from src.matching.matching_engine import MatchingPipeline

# Create a simple test record
from pymarc import Record, Field

record = Record()
record.add_field(
    Field(
        tag='245',
        indicators=['1', '0'],
        subfields=['a', 'Introduction to library science']
    )
)
record.add_field(
    Field(
        tag='020',
        indicators=[' ', ' '],
        subfields=['a', '9780838909126']
    )
)

# Wrap in MARCRecord
marc_record = MARCRecord(record)

# Match it!
pipeline = MatchingPipeline()
result = pipeline.match_record(marc_record)

print(f"Status: {result.match_status.value}")
print(f"Confidence: {result.confidence_score:.2%}")
print(f"OCLC Number: {result.worldcat_oclc_number}")
```

Run it:
```bash
docker-compose exec api python test_match.py
```

## You're Done! 🎉

The system is now running with:
- ✅ FastAPI server at http://localhost:8000
- ✅ PostgreSQL database
- ✅ Redis cache
- ✅ Celery worker for batch processing
- ✅ Flower monitoring at http://localhost:5555

## What's Next?

### Create a Batch Job

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "TEST001",
    "source_system": "Test System",
    "source_file": "/path/to/records.mrc",
    "options": {
      "auto_approve_threshold": 0.95,
      "enrichment_enabled": true
    }
  }'
```

### Check Job Status

```bash
# Get job status
curl http://localhost:8000/api/v1/jobs/JOB-<id>

# Get results
curl http://localhost:8000/api/v1/jobs/JOB-<id>/results
```

### View Statistics

```bash
curl http://localhost:8000/api/v1/stats
```

## Common Commands

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f worker
docker-compose logs -f postgres
```

### Restart Services
```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart api
```

### Stop Everything
```bash
docker-compose down

# Stop and remove volumes (fresh start)
docker-compose down -v
```

### Rebuild After Code Changes
```bash
docker-compose up -d --build
```

### Database Operations
```bash
# Access PostgreSQL
docker-compose exec postgres psql -U oclc_user -d oclc_wms

# Run migrations
docker-compose exec api python -m src.models.database migrate
```

### Redis Operations
```bash
# Access Redis CLI
docker-compose exec redis redis-cli

# Clear cache
docker-compose exec redis redis-cli FLUSHDB
```

## Troubleshooting

### Port Already in Use
If you get "port already allocated":
```bash
# Change ports in docker-compose.yml
# For API, change "8000:8000" to "8001:8000"
# For PostgreSQL, change "5432:5432" to "5433:5432"
```

### Database Connection Error
```bash
# Wait longer - PostgreSQL takes ~10 seconds to start
# Or check logs:
docker-compose logs postgres

# Restart:
docker-compose restart postgres
```

### API Won't Start
```bash
# Check logs
docker-compose logs api

# Common issue: .env file not found
cp .env.example .env

# Rebuild
docker-compose up -d --build api
```

### WorldCat API Errors
```bash
# Verify your API keys in .env
# Check rate limits - may need to wait
# Check logs for specific error:
docker-compose logs api | grep worldcat
```

## Development Workflow

### Making Code Changes

1. **Edit Code Locally**:
   - Files in `src/` are mounted as volumes
   - Changes are reflected immediately (hot reload)

2. **Test Changes**:
   ```bash
   # API has auto-reload enabled
   # Just save your file and test
   curl http://localhost:8000/...
   ```

3. **Run Tests**:
   ```bash
   docker-compose exec api pytest
   ```

4. **Format Code**:
   ```bash
   docker-compose exec api black src/
   ```

### Adding Dependencies

1. Edit `requirements.txt`
2. Rebuild:
   ```bash
   docker-compose up -d --build
   ```

## Production Considerations

Before deploying to production:

1. **Security**:
   - Change `SECRET_KEY` in .env
   - Enable HTTPS
   - Add authentication to API endpoints
   - Restrict CORS origins

2. **Performance**:
   - Increase worker count in docker-compose.yml
   - Configure database connection pooling
   - Set up load balancer

3. **Monitoring**:
   - Set up Sentry for error tracking
   - Configure Prometheus metrics
   - Set up alerts

4. **Backup**:
   - Regular PostgreSQL backups
   - Redis persistence configuration

## Getting Help

- **Documentation**: See IMPLEMENTATION_GUIDE.md for detailed docs
- **API Docs**: http://localhost:8000/docs
- **Logs**: `docker-compose logs -f`
- **Issues**: Check application logs and database logs

## System Requirements

**Minimum**:
- 4GB RAM
- 10GB disk space
- 2 CPU cores

**Recommended**:
- 8GB RAM
- 50GB disk space (for data)
- 4 CPU cores
- SSD storage

## Next Steps

1. **Read the Full Documentation**: IMPLEMENTATION_GUIDE.md
2. **Explore the API**: http://localhost:8000/docs
3. **Try Batch Processing**: Upload a MARC file
4. **Monitor Tasks**: http://localhost:5555 (Flower)
5. **Customize Configuration**: Edit .env and docker-compose.yml

---

Happy matching! 📚✨
