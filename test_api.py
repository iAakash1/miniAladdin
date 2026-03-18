#!/usr/bin/env python3
"""
Quick test script to verify OmniSignal API functionality
"""

import os
import requests
import json

# Test FRED API key
def test_fred_api():
    api_key = "6e050ad2ed98fb11706fb33f7ae2b279"
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key={api_key}&file_type=json&limit=1"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'observations' in data and len(data['observations']) > 0:
                print("✅ FRED API: Working with real data")
                print(f"   Latest 10Y Treasury: {data['observations'][0].get('value', 'N/A')}%")
                return True
            else:
                print("✅ FRED API: Connected but no data")
                return True
        else:
            print(f"❌ FRED API: Error {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ FRED API: Connection error - {e}")
        return False

# Test yfinance
def test_yfinance():
    try:
        import yfinance as yf
        ticker = yf.Ticker("AAPL")
        data = ticker.history(period="5d")
        if not data.empty:
            print("✅ yfinance: Working")
            return True
        else:
            print("❌ yfinance: No data returned")
            return False
    except Exception as e:
        print(f"❌ yfinance: Error - {e}")
        return False

# Test local API (if running)
def test_local_api():
    try:
        response = requests.get("http://localhost:8000/api/health", timeout=5)
        if response.status_code == 200:
            print("✅ Local API: Running")
            return True
        else:
            print(f"❌ Local API: Error {response.status_code}")
            return False
    except Exception as e:
        print("ℹ️  Local API: Not running (start with: uvicorn api.index:app --port 8000)")
        return False

if __name__ == "__main__":
    print("🧪 OmniSignal API Test")
    print("=" * 30)
    
    tests = [
        ("FRED API", test_fred_api),
        ("yfinance", test_yfinance),
        ("Local API", test_local_api),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\nTesting {name}...")
        results.append(test_func())
    
    print("\n" + "=" * 30)
    print(f"Results: {sum(results)}/{len(tests)} tests passed")
    
    if all(results[:2]):  # FRED and yfinance are required
        print("🎉 Core APIs are working! Ready for deployment.")
    else:
        print("⚠️  Some core APIs failed. Check your internet connection.")