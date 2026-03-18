# GitHub Repository Setup Guide

## Step 1: Create New Repository on GitHub

1. Go to [github.com/new](https://github.com/new)
2. Repository name: `omnisignal` (or your preferred name)
3. Description: `Agentic Multi-Factor Risk & Prediction Engine`
4. Set to **Public** (recommended for Vercel deployment)
5. **DO NOT** initialize with README, .gitignore, or license (we already have these)
6. Click **Create repository**

## Step 2: Connect Local Repository

After creating the repository, run these commands:

```bash
# Add your new repository as remote
git remote add origin https://github.com/iAakash1/omnisignal.git

# Push to your new repository
git push -u origin main
```

## Step 3: Verify Repository

Your repository should now contain:
- ✅ Complete OmniSignal codebase
- ✅ Dashboard (Next.js frontend)
- ✅ API (FastAPI backend)
- ✅ Documentation (README, DEPLOYMENT, etc.)
- ✅ Tests and configuration files
- ✅ No MASFIN references

## Step 4: Deploy to Vercel

1. Go to [vercel.com/new](https://vercel.com/new)
2. Click **Import Git Repository**
3. Select your `omnisignal` repository
4. Vercel will auto-detect the configuration
5. Add environment variable: `FRED_API_KEY` = your FRED API key
6. Click **Deploy**

## Step 5: Get FRED API Key (if you don't have one)

1. Go to [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html)
2. Click **Request API Key**
3. Fill out the form (it's free)
4. Copy your API key
5. Add it to Vercel environment variables

## Repository Structure

```
omnisignal/
├── api/                    # FastAPI backend
├── dashboard/              # Next.js frontend
├── src/                    # Core Python modules
├── tests/                  # Test suite
├── scripts/                # Utility scripts
├── research_vault/         # Generated reports
├── .env.example           # Environment template
├── requirements.txt       # Python dependencies
├── vercel.json           # Vercel configuration
├── README.md             # Project documentation
├── DEPLOYMENT.md         # Deployment guide
└── LICENSE               # MIT License

```

## Quick Commands

```bash
# Check git status
git status

# Add remote (replace with your actual repo URL)
git remote add origin https://github.com/iAakash1/omnisignal.git

# Push to GitHub
git push -u origin main

# Verify remote
git remote -v
```

## Next Steps

1. ✅ Create GitHub repository
2. ✅ Push code to GitHub
3. ✅ Deploy to Vercel
4. ✅ Add FRED_API_KEY to Vercel
5. ✅ Test your live application

Your app will be live at: `https://omnisignal.vercel.app` (or similar)

## Need Help?

- GitHub Issues: Create issues in your repository
- Vercel Docs: [vercel.com/docs](https://vercel.com/docs)
- FRED API: [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/)

---

**Ready to go live!** 🚀