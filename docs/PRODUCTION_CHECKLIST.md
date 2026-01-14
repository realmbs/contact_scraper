# Production Deployment Checklist

## Prerequisites
- [ ] Python 3.10 or higher installed
- [ ] 16GB RAM (8GB minimum)
- [ ] Modern CPU (4+ cores recommended)

## Environment Setup
- [ ] Clone repository
- [ ] Create virtual environment (`python3 -m venv venv`)
- [ ] Install dependencies (`pip install -r requirements.txt`)
- [ ] Install Playwright browsers (`playwright install`)
- [ ] Copy `.env.example` to `.env`
- [ ] Configure API keys (optional):
  - [ ] HUNTER_API_KEY (50 free/month)
  - [ ] ZEROBOUNCE_API_KEY (100 free)
  - [ ] NEVERBOUNCE_API_KEY (1,000 free)

## Configuration
- [ ] Set target states in config
- [ ] Set program type (law schools, paralegal, or both)
- [ ] Configure rate limiting (default: 2s)
- [ ] Enable browser pooling for performance (`USE_BROWSER_POOL=true`)

## Testing
- [ ] Run unit tests (`pytest tests/ -v`)
- [ ] Run small-scale test (5 institutions)
- [ ] Verify Excel output format

## Performance Tuning
- [ ] Review SCALING_GUIDE.md for optimization tips
- [ ] Configure async workers (default: 6)
- [ ] Enable browser pooling (20-30% speedup)
- [ ] Monitor memory usage (<8GB peak)

## Production Run
- [ ] Set target states (all 50 or specific)
- [ ] Choose program types
- [ ] Start scraping (`python main.py`)
- [ ] Monitor progress in logs/
- [ ] Review output Excel workbook
- [ ] Validate contact quality (>80% email validity)

## Post-Processing
- [ ] Review statistics sheet
- [ ] Compare with existing database (if applicable)
- [ ] Filter by confidence score (>60 recommended)
- [ ] Manual review of low-confidence contacts (<60)
