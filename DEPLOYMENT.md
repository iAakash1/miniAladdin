# OmniSignal Deployment Guide

## Prerequisites

- GitHub account
- Vercel account (free tier works)
- FRED API key ([get one free here](https://fred.stlouisfed.org/docs/api/api_key.html))

## Local Development

### 1. Install Python Dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

```bash
cp .env.example .env
# Edit .env and add your FRED_API_KEY
```

### 3. Start the API Server

```bash
uvicorn api.index:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

### 4. Start the Dashboard (in a new terminal)

```bash
cd dashboard
npm install
npm run dev
```

The dashboard will be available at `http://localhost:3000`

### 5. Test the API

```bash
# Health check
curl http://localhost:8000/api/health

# Macro risk data
curl http://localhost:8000/api/macro

# Full research (takes ~5-7s)
curl http://localhost:8000/api/research/NVDA

# Fast mode (takes ~3-4s, skips sentiment)
curl http://localhost:8000/api/research/NVDA?fast=true
```

## Deploying to Vercel

### Step 1: Push to GitHub

```bash
# Create a new repository on GitHub first, then:
git remote add origin https://github.com/iAakash1/omnisignal.git
git branch -M main
git push -u origin main
```

### Step 2: Import to Vercel

1. Go to [vercel.com/new](https://vercel.com/new)
2. Click "Import Git Repository"
3. Select your GitHub repository
4. Vercel will auto-detect the configuration from `vercel.json`

### Step 3: Configure Environment Variables

In the Vercel dashboard:

1. Go to **Settings** → **Environment Variables**
2. Add the following:

| Variable | Value | Environment |
|---|---|---|
| `FRED_API_KEY` | Your FRED API key | Production, Preview, Development |

### Step 4: Deploy

Click **Deploy** and wait ~2-3 minutes for the build to complete.

Your app will be live at: `https://your-project.vercel.app`

## API Endpoints

| Endpoint | Method | Description | Response Time |
|---|---|---|---|
| `/api/health` | GET | Health check | <1s |
| `/api/macro` | GET | Systemic Risk Multiplier + macro indicators | ~2s |
| `/api/research/{ticker}` | GET | Full OmniSignal analysis | ~5-7s |
| `/api/research/{ticker}?fast=true` | GET | Fast mode (no sentiment) | ~3-4s |

## Performance Optimization

The API is optimized for Vercel's 10-second timeout:

- **Macro endpoint**: ~2s (FRED API calls)
- **Fast research**: ~3-4s (macro + technicals only)
- **Full research**: ~5-7s (macro + technicals + sentiment)

All endpoints include graceful fallbacks if external APIs fail.

## Monitoring

Check your deployment logs in Vercel:

1. Go to your project dashboard
2. Click **Deployments**
3. Select a deployment
4. View **Function Logs** for API calls

## Troubleshooting

### API returns 500 errors

- Check that `FRED_API_KEY` is set in Vercel environment variables
- Verify the key is valid at [fred.stlouisfed.org](https://fred.stlouisfed.org)

### Dashboard shows "Failed to fetch"

- Ensure the API is deployed and healthy: visit `/api/health`
- Check CORS settings in `api/index.py`

### Slow response times

- Use `?fast=true` query parameter to skip sentiment analysis
- Consider caching macro data (updates infrequently)

## Custom Domain (Optional)

1. Go to **Settings** → **Domains**
2. Add your custom domain
3. Follow DNS configuration instructions

## Continuous Deployment

Vercel automatically deploys on every push to `main`:

```bash
git add .
git commit -m "feat: add new feature"
git push origin main
```

Your changes will be live in ~2-3 minutes.

---

**Need help?** Check the [Vercel documentation](https://vercel.com/docs) or open an issue on GitHub.
