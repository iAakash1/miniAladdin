"""
OmniSignal Report Generator
Generates Markdown research reports in the research_vault directory.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models import (
    AggregateSentiment,
    MacroStatus,
    OmniSignalReport,
    RiskAssessment,
    SentimentLabel,
    TechnicalAnalysis,
)

# Default vault location relative to project root
DEFAULT_VAULT = Path(__file__).parent.parent / "research_vault"


class OmniSignalReportGenerator:
    """Generates Markdown reports from OmniSignalReport data."""

    def __init__(self, vault_dir: Optional[Path] = None):
        self.vault_dir = vault_dir or DEFAULT_VAULT
        self.vault_dir.mkdir(parents=True, exist_ok=True)

    def _format_header(self, report: OmniSignalReport) -> str:
        """Generate the report header."""
        return f"""# 📊 OmniSignal Report: {report.ticker}

| Field | Value |
|---|---|
| **Ticker** | {report.ticker} |
| **Generated** | {report.generated_at.strftime("%Y-%m-%d %H:%M:%S")} |
| **OmniSignal Version** | {report.version} |
| **Verdict** | **{report.omnisignal_verdict.value}** |
| **Confidence** | {report.confidence:.0%} |

---
"""

    def _format_macro(self, macro: Optional[RiskAssessment]) -> str:
        """Format the macro environment section."""
        if macro is None:
            return "## 🌍 Macro Environment\n\n*No macro data available.*\n\n---\n"

        status_emoji = {
            MacroStatus.STABLE: "🟢",
            MacroStatus.ELEVATED: "🟡",
            MacroStatus.CRITICAL: "🔴",
            MacroStatus.DATA_ERROR: "⚪",
        }

        lines = [
            "## 🌍 Macro Environment\n",
            f"**Status:** {status_emoji.get(macro.status, '⚪')} {macro.status.value}\n",
            f"**Systemic Risk Multiplier:** `{macro.risk_multiplier}`\n",
        ]

        if macro.indicators:
            lines.append(f"**Yield Spread (10Y-2Y):** {macro.indicators.yield_spread:.2f}%\n")
            lines.append(f"**Inflation (YoY CPI):** {macro.indicators.inflation_rate:.2f}%\n")
            if macro.indicators.fed_funds_rate is not None:
                lines.append(f"**Fed Funds Rate:** {macro.indicators.fed_funds_rate:.2f}%\n")

        if macro.recession_warning:
            lines.append("\n> ⚠️ **RECESSION WARNING**: Yield curve is inverted. "
                         "Historically, this has preceded recessions by 6–18 months.\n")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _format_technicals(self, tech: Optional[TechnicalAnalysis]) -> str:
        """Format the technical analysis section."""
        if tech is None:
            return "## 📈 Technical Analysis\n\n*No technical data available.*\n\n---\n"

        lines = ["## 📈 Technical Analysis\n"]

        if tech.current_price is not None:
            lines.append(f"**Current Price:** ${tech.current_price:,.2f}\n")

        lines.append("\n| Indicator | Value |")
        lines.append("|---|---|")

        indicators = [
            ("5-Day Return", f"{tech.return_5d:.2%}" if tech.return_5d is not None else "N/A"),
            ("21-Day Return", f"{tech.return_21d:.2%}" if tech.return_21d is not None else "N/A"),
            ("Volatility (Ann.)", f"{tech.volatility:.2%}" if tech.volatility is not None else "N/A"),
            ("Sharpe Ratio", f"{tech.sharpe_ratio:.4f}" if tech.sharpe_ratio is not None else "N/A"),
            ("Sortino Ratio", f"{tech.sortino_ratio:.4f}" if tech.sortino_ratio is not None else "N/A"),
            ("RSI-14", f"{tech.rsi_14:.2f}" if tech.rsi_14 is not None else "N/A"),
            ("Max Drawdown", f"{tech.max_drawdown:.2%}" if tech.max_drawdown is not None else "N/A"),
            ("Momentum (21d)", f"${tech.momentum:,.2f}" if tech.momentum is not None else "N/A"),
        ]

        for name, value in indicators:
            lines.append(f"| {name} | {value} |")

        lines.append(f"\n**Raw Signal:** {tech.raw_signal.value if tech.raw_signal else 'N/A'}")
        lines.append(f"**Risk-Adjusted Signal:** {tech.risk_adjusted_signal.value if tech.risk_adjusted_signal else 'N/A'}\n")
        lines.append("\n---\n")
        return "\n".join(lines)

    def _format_sentiment(self, sentiment: Optional[AggregateSentiment]) -> str:
        """Format the sentiment analysis section."""
        if sentiment is None or sentiment.headline_count == 0:
            return "## 🗞️ Sentiment Edge\n\n*No sentiment data available.*\n\n---\n"

        label_emoji = {
            SentimentLabel.BULLISH: "🟢",
            SentimentLabel.BEARISH: "🔴",
            SentimentLabel.NEUTRAL: "⚪",
        }

        lines = [
            "## 🗞️ Sentiment Edge\n",
            f"**Headlines Analyzed:** {sentiment.headline_count}",
            f"**Average Sentiment Score:** {sentiment.average_score:.4f}",
            f"**Dominant Sentiment:** {label_emoji.get(sentiment.dominant_label, '⚪')} "
            f"{sentiment.dominant_label.value}\n",
            "### Headlines\n",
            "| # | Headline | Score | Label |",
            "|---|---|---|---|",
        ]

        for i, h in enumerate(sentiment.headlines, 1):
            emoji = label_emoji.get(h.label, "⚪")
            lines.append(f"| {i} | {h.headline} | {h.score:+.4f} | {emoji} {h.label.value} |")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _format_verdict(self, report: OmniSignalReport) -> str:
        """Format the final OmniSignal verdict."""
        verdict_emoji = {
            "Strong Buy": "🚀",
            "Buy": "📈",
            "Hold": "➡️",
            "Sell": "📉",
            "Strong Sell": "🔻",
        }

        emoji = verdict_emoji.get(report.omnisignal_verdict.value, "❓")

        return f"""## 🎯 OmniSignal Verdict

### {emoji} {report.omnisignal_verdict.value}

**Confidence:** {report.confidence:.0%}

**Rationale:** {report.rationale}

---

*Generated by OmniSignal v{report.version} — Agentic Multi-Factor Risk Engine*
*This report is for research and educational purposes only. Not financial advice.*
"""

    def generate(
        self,
        report: OmniSignalReport,
        pdf: bool = True,
    ) -> str:
        """
        Generate a full Markdown report and save to the vault.
        Optionally generates a PDF version alongside.

        Returns the file path of the generated Markdown report.
        """
        content = ""
        content += self._format_header(report)
        content += self._format_macro(report.macro)
        content += self._format_technicals(report.technicals)
        content += self._format_sentiment(report.sentiment)
        content += self._format_verdict(report)

        # Write Markdown to vault
        date_str = report.generated_at.strftime("%Y%m%d_%H%M%S")
        filename = f"{report.ticker}_omnisignal_{date_str}.md"
        filepath = self.vault_dir / filename

        filepath.write_text(content, encoding="utf-8")
        print(f"[OmniSignal] Markdown report saved: {filepath}")

        # Generate PDF version
        if pdf:
            pdf_path = self.generate_pdf(report, date_str)
            print(f"[OmniSignal] PDF report saved: {pdf_path}")

        return str(filepath)

    def generate_pdf(self, report: OmniSignalReport, date_str: Optional[str] = None) -> str:
        """
        Generate a PDF version of the OmniSignal report.

        Uses fpdf2 to create a clean, professional PDF.
        Returns the file path of the generated PDF.
        """
        import re
        try:
            from fpdf import FPDF
        except ImportError:
            print("[OmniSignal] fpdf2 not installed. Install with: pip install fpdf2")
            return ""

        if date_str is None:
            date_str = report.generated_at.strftime("%Y%m%d_%H%M%S")

        def clean(text: str) -> str:
            """Strip emoji and non-latin-1 characters for PDF rendering."""
            return re.sub(
                r'[^\x20-\x7E\n\t]', '', text
            ).strip()

        pdf_doc = FPDF()
        pdf_doc.set_auto_page_break(auto=True, margin=15)
        pdf_doc.add_page()

        # Title
        pdf_doc.set_font("Helvetica", "B", 20)
        pdf_doc.cell(0, 12, f"OmniSignal Report: {report.ticker}", new_x="LMARGIN", new_y="NEXT")
        pdf_doc.ln(4)

        # Summary table
        pdf_doc.set_font("Helvetica", "", 10)
        summary_items = [
            ("Ticker", report.ticker),
            ("Generated", report.generated_at.strftime("%Y-%m-%d %H:%M:%S")),
            ("Version", report.version),
            ("Verdict", report.omnisignal_verdict.value),
            ("Confidence", f"{report.confidence:.0%}"),
        ]
        for label, value in summary_items:
            pdf_doc.set_font("Helvetica", "B", 10)
            pdf_doc.cell(45, 7, f"{label}:")
            pdf_doc.set_font("Helvetica", "", 10)
            pdf_doc.cell(0, 7, str(value), new_x="LMARGIN", new_y="NEXT")

        pdf_doc.ln(6)

        # ── Macro Section ────────────────────────────────────────────
        pdf_doc.set_font("Helvetica", "B", 14)
        pdf_doc.cell(0, 10, "Macro Environment", new_x="LMARGIN", new_y="NEXT")
        pdf_doc.set_font("Helvetica", "", 10)

        if report.macro:
            macro_lines = [
                f"Status: {report.macro.status.value}",
                f"Systemic Risk Multiplier: {report.macro.risk_multiplier}",
            ]
            if report.macro.indicators:
                macro_lines.append(
                    f"Yield Spread (10Y-2Y): {report.macro.indicators.yield_spread:.2f}%"
                )
                macro_lines.append(
                    f"Inflation (YoY CPI): {report.macro.indicators.inflation_rate:.2f}%"
                )
                if report.macro.indicators.fed_funds_rate is not None:
                    macro_lines.append(
                        f"Fed Funds Rate: {report.macro.indicators.fed_funds_rate:.2f}%"
                    )
            if report.macro.recession_warning:
                macro_lines.append(
                    "WARNING: Yield curve is inverted — recession signal active"
                )
            for line in macro_lines:
                pdf_doc.cell(0, 6, clean(line), new_x="LMARGIN", new_y="NEXT")
        else:
            pdf_doc.cell(0, 6, "No macro data available.", new_x="LMARGIN", new_y="NEXT")

        pdf_doc.ln(6)

        # ── Technicals Section ───────────────────────────────────────
        pdf_doc.set_font("Helvetica", "B", 14)
        pdf_doc.cell(0, 10, "Technical Analysis", new_x="LMARGIN", new_y="NEXT")
        pdf_doc.set_font("Helvetica", "", 10)

        if report.technicals:
            tech = report.technicals
            if tech.current_price is not None:
                pdf_doc.set_font("Helvetica", "B", 10)
                pdf_doc.cell(0, 7, f"Current Price: ${tech.current_price:,.2f}", new_x="LMARGIN", new_y="NEXT")
                pdf_doc.set_font("Helvetica", "", 10)

            indicators = [
                ("5-Day Return", f"{tech.return_5d:.2%}" if tech.return_5d is not None else "N/A"),
                ("21-Day Return", f"{tech.return_21d:.2%}" if tech.return_21d is not None else "N/A"),
                ("Volatility", f"{tech.volatility:.2%}" if tech.volatility is not None else "N/A"),
                ("Sharpe Ratio", f"{tech.sharpe_ratio:.4f}" if tech.sharpe_ratio is not None else "N/A"),
                ("Sortino Ratio", f"{tech.sortino_ratio:.4f}" if tech.sortino_ratio is not None else "N/A"),
                ("RSI-14", f"{tech.rsi_14:.2f}" if tech.rsi_14 is not None else "N/A"),
                ("Max Drawdown", f"{tech.max_drawdown:.2%}" if tech.max_drawdown is not None else "N/A"),
                ("Momentum (21d)", f"${tech.momentum:,.2f}" if tech.momentum is not None else "N/A"),
            ]
            for name, value in indicators:
                pdf_doc.cell(60, 6, f"  {name}:")
                pdf_doc.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")

            pdf_doc.ln(3)
            pdf_doc.cell(0, 6,
                f"Raw Signal: {tech.raw_signal.value if tech.raw_signal else 'N/A'}",
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf_doc.cell(0, 6,
                f"Risk-Adjusted Signal: {tech.risk_adjusted_signal.value if tech.risk_adjusted_signal else 'N/A'}",
                new_x="LMARGIN", new_y="NEXT",
            )
        else:
            pdf_doc.cell(0, 6, "No technical data available.", new_x="LMARGIN", new_y="NEXT")

        pdf_doc.ln(6)

        # ── Sentiment Section ────────────────────────────────────────
        pdf_doc.set_font("Helvetica", "B", 14)
        pdf_doc.cell(0, 10, "Sentiment Edge", new_x="LMARGIN", new_y="NEXT")
        pdf_doc.set_font("Helvetica", "", 10)

        if report.sentiment and report.sentiment.headline_count > 0:
            pdf_doc.cell(0, 6,
                f"Headlines Analyzed: {report.sentiment.headline_count}",
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf_doc.cell(0, 6,
                f"Average Score: {report.sentiment.average_score:.4f}",
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf_doc.cell(0, 6,
                f"Dominant Sentiment: {report.sentiment.dominant_label.value}",
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf_doc.ln(3)

            for i, h in enumerate(report.sentiment.headlines, 1):
                headline_text = clean(h.headline)
                if len(headline_text) > 80:
                    headline_text = headline_text[:77] + "..."
                pdf_doc.cell(0, 5,
                    f"  {i}. [{h.label.value}] {headline_text} (score: {h.score:+.4f})",
                    new_x="LMARGIN", new_y="NEXT",
                )
        else:
            pdf_doc.cell(0, 6, "No sentiment data available.", new_x="LMARGIN", new_y="NEXT")

        pdf_doc.ln(6)

        # ── Verdict Section ──────────────────────────────────────────
        pdf_doc.set_font("Helvetica", "B", 16)
        pdf_doc.cell(0, 10,
            f"OmniSignal Verdict: {report.omnisignal_verdict.value}",
            new_x="LMARGIN", new_y="NEXT",
        )
        pdf_doc.set_font("Helvetica", "", 10)
        pdf_doc.cell(0, 7, f"Confidence: {report.confidence:.0%}", new_x="LMARGIN", new_y="NEXT")
        pdf_doc.ln(3)
        if report.rationale:
            pdf_doc.multi_cell(0, 5, f"Rationale: {clean(report.rationale)}")

        pdf_doc.ln(8)
        pdf_doc.set_font("Helvetica", "I", 8)
        pdf_doc.cell(0, 5,
            f"Generated by OmniSignal v{report.version} | For research/educational purposes only.",
            new_x="LMARGIN", new_y="NEXT",
        )

        # Save PDF
        pdf_filename = f"{report.ticker}_omnisignal_{date_str}.pdf"
        pdf_path = self.vault_dir / pdf_filename
        pdf_doc.output(str(pdf_path))
        return str(pdf_path)

    def generate_from_components(
        self,
        ticker: str,
        macro: Optional[RiskAssessment] = None,
        technicals: Optional[TechnicalAnalysis] = None,
        sentiment: Optional[AggregateSentiment] = None,
        verdict_override: Optional[str] = None,
    ) -> str:
        """
        Build and generate a report from individual components.
        """
        from src.models import SignalVerdict

        report = OmniSignalReport(
            ticker=ticker.upper(),
            macro=macro,
            technicals=technicals,
            sentiment=sentiment,
            omnisignal_verdict=SignalVerdict(verdict_override) if verdict_override else SignalVerdict.HOLD,
        )
        return self.generate(report)

