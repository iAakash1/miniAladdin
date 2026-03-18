# 🎮 Demo Mode - No API Keys Required!

## ✨ What is Demo Mode?

miniAladdin works **out of the box** without any API keys! Demo mode provides realistic mock data so you can:

- ✅ Deploy immediately to Vercel
- ✅ Test all features and UI
- ✅ Show the platform to others
- ✅ Develop and iterate quickly

## 🔄 Demo vs Production Data

| Feature | Demo Mode | Production Mode |
|---|---|---|
| **Macro Risk** | Mock Federal Reserve data | Real FRED API data |
| **Technical Analysis** | Real stock data (yfinance) | Real stock data (yfinance) |
| **Sentiment Analysis** | Real news headlines | Real news headlines |
| **Dashboard** | Fully functional | Fully functional |
| **API Speed** | Fast (~2-3s) | Fast (~2-5s) |

## 🚀 Deploy in Demo Mode

1. **Push to GitHub** ✅ (Already done!)
2. **Deploy to Vercel**: [vercel.com/new](https://vercel.com/new)
3. **Import repository**: Select `miniAladdin`
4. **Click Deploy** - No environment variables needed!

## 📊 Demo Data Details

### Macro Risk (Demo)
```json
{
  "risk_multiplier": 1.15,
  "stats": {
    "status": "DEMO_MODE",
    "yield_curve_inverted": false,
    "inflation_rate": 3.2,
    "fed_funds_rate": 5.25,
    "note": "Get a free FRED API key at fred.stlouisfed.org"
  }
}
```

### What's Real vs Mock

**Real Data (Always):**
- ✅ Stock prices and technical indicators
- ✅ News headlines and sentiment scores
- ✅ All calculations and risk adjustments
- ✅ Dashboard functionality

**Mock Data (Demo Mode Only):**
- 🎭 Federal Reserve economic indicators
- 🎭 Treasury yield curves
- 🎭 Inflation and interest rate data

## 🔑 Upgrade to Production

When ready for real FRED data:

1. Get free API key: [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html)
2. Add to Vercel: **Settings** → **Environment Variables**
3. Name: `FRED_API_KEY`, Value: your key
4. Redeploy - now using real Federal Reserve data!

## 🎯 Perfect for:

- **Demos and presentations**
- **Development and testing**
- **Proof of concept**
- **Learning the platform**
- **Immediate deployment**

## 🧪 Test Your Demo App

Once deployed, try these:

```bash
# Health check (shows demo mode status)
https://your-app.vercel.app/api/health

# Macro data (demo Federal Reserve data)
https://your-app.vercel.app/api/macro

# Full analysis (real stock data + demo macro)
https://your-app.vercel.app/api/research/NVDA
```

## 💡 Pro Tip

Demo mode is perfect for:
- Getting stakeholder buy-in
- Testing deployment pipeline
- Developing new features
- Training users on the interface

**Ready to deploy?** Your app works perfectly in demo mode! 🚀