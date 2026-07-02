/* Keyword classifier: assigns a category when the source feed is broad.
   Rule order matters — earlier rules win. */

import type { NewsCategory } from '../types'

const RULES: Array<{ category: NewsCategory; pattern: RegExp }> = [
  {
    category: 'crypto',
    pattern:
      /\b(bitcoin|btc|ethereum|ether|crypto|stablecoin|blockchain|binance|coinbase|altcoin|defi|nft)\b/i,
  },
  {
    category: 'economy',
    pattern:
      /\b(fed|federal reserve|inflation|cpi|ppi|gdp|jobs report|payrolls|unemployment|recession|treasury|yield[s]?|rate (cut|hike)|interest rate|tariff|central bank|ecb|bank of (england|japan)|fomc|stimulus|deficit)\b/i,
  },
  {
    category: 'technology',
    pattern:
      /\b(ai|artificial intelligence|chip[s]?|semiconductor|software|cloud|cybersecurity|data center|robotics|quantum|smartphone|streaming|social media|gadget)\b/i,
  },
  {
    category: 'companies',
    pattern:
      /\b(earnings|ipo|merger|acquisition|acquire[sd]?|buyback|dividend|guidance|ceo|cfo|lawsuit|antitrust|layoffs|restructuring|spin[- ]?off|stake|takeover)\b/i,
  },
]

export function classify(title: string, summary: string, fallback: NewsCategory | null): NewsCategory {
  const haystack = `${title} ${summary}`
  for (const rule of RULES) {
    if (rule.pattern.test(haystack)) return rule.category
  }
  return fallback ?? 'markets'
}
