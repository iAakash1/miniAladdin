# Pre-Deployment Checklist ✅

## Local Testing

- [x] Dashboard builds successfully (`npm run build` in dashboard/)
- [ ] Python tests pass (`pytest tests/ -v`)
- [ ] API server starts (`uvicorn api.index:app --port 8000`)
- [ ] Dashboard runs locally (`npm run dev` in dashboard/)
- [ ] Environment variables configured (`.env` file created)

## Code Quality

- [x] All files committed to git
- [x] `.gitignore` properly configured
- [x] No sensitive data in repository (API keys, secrets)
- [x] Documentation complete (README.md, DEPLOYMENT.md)
- [x] Dependencies documented (requirements.txt, package.json)

## Vercel Configuration

- [x] `vercel.json` configured
- [x] API routes properly set up (`/api/*`)
- [x] Build commands specified
- [x] Environment variable examples provided

## Required Before Deployment

### 1. Get FRED API Key
- [ ] Sign up at https://fred.stlouisfed.org/docs/api/api_key.html
- [ ] Copy your API key
- [ ] Add to `.env` file locally: `FRED_API_KEY=your_key_here`

### 2. Test Locally
```bash
# Terminal 1: Start API
uvicorn api.index:app --reload --port 8000

# Terminal 2: Start Dashboard
cd dashboard && npm run dev

# Terminal 3: Test endpoints
curl http://localhost:8000/api/health
curl http://localhost:8000/api/macro
```

### 3. Push to GitHub
```bash
git add .
git commit -m "feat: OmniSignal risk engine ready for deployment"
git push origin main
```

### 4. Deploy to Vercel
1. Go to https://vercel.com/new
2. Import your GitHub repository
3. Vercel auto-detects configuration
4. Add environment variable: `FRED_API_KEY`
5. Click Deploy

### 5. Verify Deployment
- [ ] Visit your Vercel URL
- [ ] Test `/api/health` endpoint
- [ ] Test `/api/macro` endpoint
- [ ] Test full research: `/api/research/NVDA`
- [ ] Test dashboard UI

## Post-Deployment

- [ ] Monitor function logs in Vercel dashboard
- [ ] Test with multiple tickers (AAPL, MSFT, TSLA, etc.)
- [ ] Verify response times (<10s)
- [ ] Check error handling (invalid tickers, API failures)

## Troubleshooting

### Dashboard shows "Failed to fetch"
- Check API is deployed and healthy
- Verify CORS settings in `api/index.py`
- Check browser console for errors

### API returns 500 errors
- Verify `FRED_API_KEY` is set in Vercel
- Check function logs in Vercel dashboard
- Test FRED API key at https://fred.stlouisfed.org

### Slow response times
- Use `?fast=true` parameter to skip sentiment
- Consider caching macro data
- Check Vercel function logs for bottlenecks

## Quick Commands

```bash
# Build dashboard
cd dashboard && npm run build

# Run tests
pytest tests/ -v --cov=src

# Start API locally
uvicorn api.index:app --reload --port 8000

# Deploy script
bash scripts/deploy.sh

# Check git status
git status

# Stage all changes
git add .

# Commit
git commit -m "feat: ready for deployment"

# Push
git push origin main
```

## Success Criteria

✅ Dashboard builds without errors
✅ All API endpoints respond correctly
✅ Response times under 10 seconds
✅ Error handling works gracefully
✅ Documentation is complete
✅ No sensitive data in repository

---

**Ready to deploy?** Follow the steps in `DEPLOYMENT.md`
