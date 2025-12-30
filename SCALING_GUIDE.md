# Parallelization Scaling Guide

## Current System Capacity

**Hardware Profile**:
- CPU: 8 cores (8 threads)
- RAM: 16 GB total (2.8 GB available currently)
- Current usage: 82.6% RAM utilized

**Current Settings** (Conservative):
```
Institution parallelization:  6 workers
Profile link concurrency:     3 workers
Directory concurrency:        3 workers
Browser pool size:            3 browsers
```

---

## Recommended Scaling Options

### Option 1: MODERATE (Recommended for Safety)
**Best for**: Stable performance with minimal risk of crashes

```bash
# Edit .env file:
PROFILE_LINK_CONCURRENCY=5     # 3 → 5 (67% increase)
DIRECTORY_CONCURRENCY=5         # 3 → 5 (67% increase)
BROWSER_POOL_SIZE=5             # 3 → 5 (67% increase)
```

```python
# Edit main.py line 313:
contacts = run_async_scraping(targets, max_institutions=max_institutions, max_parallel=8)  # 6 → 8
```

**Expected Impact**:
- Speedup: **+30-40%** (6.13min → ~4.5min on Berkeley)
- Memory: **~1.2 GB** (within 2.8 GB available)
- Risk: **Low** (plenty of headroom)

---

### Option 2: AGGRESSIVE (Max Performance)
**Best for**: When you need maximum speed and have closed other applications

```bash
# Edit .env file:
PROFILE_LINK_CONCURRENCY=8     # 3 → 8 (167% increase)
DIRECTORY_CONCURRENCY=8         # 3 → 8 (167% increase)
BROWSER_POOL_SIZE=6             # 3 → 6 (100% increase)
```

```python
# Edit main.py line 313:
contacts = run_async_scraping(targets, max_institutions=max_institutions, max_parallel=10)  # 6 → 10
```

**Expected Impact**:
- Speedup: **+60-80%** (6.13min → ~3.5min on Berkeley)
- Memory: **~1.8 GB** (tight but safe if other apps closed)
- Risk: **Medium** (may swap if other apps open)

---

### Option 3: EXTREME (Use with Caution)
**Best for**: Maximum speed, only when system is dedicated to scraping

```bash
# Edit .env file:
PROFILE_LINK_CONCURRENCY=12    # 3 → 12 (300% increase)
DIRECTORY_CONCURRENCY=12        # 3 → 12 (300% increase)
BROWSER_POOL_SIZE=8             # 3 → 8 (167% increase)
```

```python
# Edit main.py line 313:
contacts = run_async_scraping(targets, max_institutions=max_institutions, max_parallel=12)  # 6 → 12
```

**Expected Impact**:
- Speedup: **+100-120%** (6.13min → ~2.8min on Berkeley)
- Memory: **~2.4 GB** (at limit, may cause swapping)
- Risk: **High** (may crash if memory runs out)

---

## How to Apply Changes

### Step 1: Edit .env file
```bash
nano .env

# Add or update these lines:
PROFILE_LINK_CONCURRENCY=5
DIRECTORY_CONCURRENCY=5
BROWSER_POOL_SIZE=5
```

### Step 2: Edit main.py
```bash
nano main.py

# Find line 313 (around "run_async_scraping")
# Change: max_parallel=6
# To:     max_parallel=8  (or 10, or 12 depending on option)
```

### Step 3: Test incrementally
```bash
# Start conservative, test, then increase
source venv/bin/activate
python test_berkeley_performance.py
```

---

## Bottleneck Analysis

### Current Bottlenecks (in priority order):

1. **Profile Link Visiting** (60% of time)
   - **Where**: `PROFILE_LINK_CONCURRENCY` in .env
   - **Safe range**: 3-12 workers
   - **Best value**: 5-8 workers
   - **Impact**: High (direct speedup)

2. **Directory Processing** (20% of time)
   - **Where**: `DIRECTORY_CONCURRENCY` in .env
   - **Safe range**: 3-12 workers
   - **Best value**: 5-8 workers
   - **Impact**: Medium

3. **Institution Parallelization** (15% of time)
   - **Where**: `max_parallel` parameter in main.py:313
   - **Safe range**: 6-12 workers
   - **Best value**: 8-10 workers
   - **Impact**: Medium

4. **Browser Pool** (5% of time)
   - **Where**: `BROWSER_POOL_SIZE` in .env
   - **Safe range**: 3-8 browsers
   - **Best value**: 5-6 browsers
   - **Impact**: Low (mainly saves launch overhead)

---

## Memory Calculation Formula

```
Estimated Peak Memory = (Browser Pool Size × 150 MB) + (200 MB overhead)

Examples:
- 3 browsers:  ~650 MB  ✅ Very safe
- 5 browsers:  ~950 MB  ✅ Safe
- 8 browsers:  ~1.4 GB  ⚠️ Tight
- 12 browsers: ~2.0 GB  ❌ May crash
```

---

## Performance Expectations

### Berkeley Law School (24 contacts, baseline: 21 min → 6.13 min with current settings)

| Configuration | Expected Time | Speedup vs Baseline | Risk |
|---------------|---------------|---------------------|------|
| Current (3/3/3/6) | 6.13 min | 3.42x | ✅ None |
| Moderate (5/5/5/8) | ~4.5 min | 4.67x | ✅ Low |
| Aggressive (8/8/6/10) | ~3.5 min | 6.00x | ⚠️ Medium |
| Extreme (12/12/8/12) | ~2.8 min | 7.50x | ❌ High |

### Diminishing Returns

After **8 workers per setting**, you hit diminishing returns:
- Network becomes bottleneck (bandwidth limits)
- Rate limiting kicks in (domains start blocking)
- Context switching overhead increases

**Sweet spot**: 5-8 workers per setting

---

## Monitoring Performance

### Watch for these warning signs:

1. **Memory Swapping** (system becomes sluggish)
   ```bash
   # Monitor memory during scraping
   watch -n 1 'free -h'
   ```

2. **HTTP 429 Errors** (too many requests)
   - Check logs for "Rate limit" or "429" errors
   - Reduce parallelization if you see these

3. **Browser Crashes** (Playwright errors)
   - "Browser disconnected" errors
   - Reduce `BROWSER_POOL_SIZE`

4. **Timeouts Increasing** (network congestion)
   - More timeout errors in logs
   - Network is saturated

---

## Recommended Approach

### Phase 1: Start Moderate
```bash
PROFILE_LINK_CONCURRENCY=5
DIRECTORY_CONCURRENCY=5
BROWSER_POOL_SIZE=5
max_parallel=8
```

### Phase 2: Test on Berkeley
```bash
python test_berkeley_performance.py
# Target: < 5 minutes, no errors
```

### Phase 3: Increase if Successful
```bash
# If Phase 2 succeeds, bump to aggressive:
PROFILE_LINK_CONCURRENCY=8
DIRECTORY_CONCURRENCY=8
max_parallel=10
```

### Phase 4: Monitor Full Run
```bash
# Run 10-20 institutions and watch memory
python main.py
# Select 10-15 institutions
# Watch htop or Activity Monitor
```

---

## Quick Reference

### Conservative (Current)
- Institution: 6
- Profile: 3
- Directory: 3
- Browsers: 3
- **Use when**: Default, safest option

### Moderate (Recommended)
- Institution: 8
- Profile: 5
- Directory: 5
- Browsers: 5
- **Use when**: You want better performance with low risk

### Aggressive (Fast)
- Institution: 10
- Profile: 8
- Directory: 8
- Browsers: 6
- **Use when**: System is mostly idle, need speed

### Extreme (Maximum)
- Institution: 12
- Profile: 12
- Directory: 12
- Browsers: 8
- **Use when**: Dedicated system, close all other apps first

---

## Rollback Instructions

If you encounter problems, revert to defaults:

```bash
# .env file
PROFILE_LINK_CONCURRENCY=3
DIRECTORY_CONCURRENCY=3
BROWSER_POOL_SIZE=3

# main.py line 313
max_parallel=6
```

Then restart Python and try again.
