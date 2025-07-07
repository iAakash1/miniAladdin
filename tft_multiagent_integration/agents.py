from crewai import Agent
from typing import List, Optional
from enhanced_forecasting_analyst import create_enhanced_forecasting_analyst

# --- Postmortem Crew Agents -------------------------------------------------

def get_postmortem_agents() -> List[Agent]:
    """Return agents for the Postmortem Crew (copied from notebook)."""
    delisted_historian = Agent(
        role="Delisted Historian",
        goal="Surface systemic risks and patterns from companies that failed or were delisted.",
        backstory=(
            "You are a financial historian reconstructing why companies disappeared from the market."
            " Focus on the provided headlines (Primary Data) and extract red-flag signals."
        ),
        verbose=True,
    )

    failure_pattern_analyst = Agent(
        role="Failure Pattern Analyst",
        goal="Identify recurring signs of corporate collapse using real-world news from delisted stocks.",
        backstory=(
            "You are a forensic analyst trained to identify warning signs in failing companies."
        ),
        verbose=True,
    )

    confirmation_sentinel = Agent(
        role="Confirmation Sentinel",
        goal="Detect signs of confirmation bias and inject counter-examples to protect screening assumptions.",
        backstory=(
            "You are a behavioral finance watchdog tasked with enforcing objectivity."
        ),
        verbose=True,
    )

    news_sentiment_analyst = Agent(
        role="News Sentiment Analyst",
        goal="Analyze aggregated news headlines from delisted companies to uncover sentiment trends.",
        backstory=(
            "You are a market-sentiment analyst focused on reverse-engineering risk themes from real news data."
        ),
        verbose=True,
    )

    summary_analyst = Agent(
        role="Summary Analyst",
        goal="Consolidate insights from the Postmortem Crew into a structured briefing for the next crew.",
        backstory="You are the final synthesizer of the Postmortem Crew.",
        verbose=True,
    )

    return [
        delisted_historian,
        failure_pattern_analyst,
        confirmation_sentinel,
        news_sentiment_analyst,
        summary_analyst,
    ]


# --- Analysis Crew Agents ----------------------------------------------------

def get_analysis_agents(evaluation_start_date: str) -> List[Agent]:
    """Return agents for the Analysis Crew, including the TFT-enhanced forecasting analyst."""
    # Place-holder simple agents for brevity – swap in your detailed ones if needed.
    backtesting_agent = Agent(
        role="Quantitative Backtesting Analyst",
        goal="Conduct rigorous short-term backtests of candidate tickers.",
        backstory="You calculate risk/return metrics with strict bias control.",
        verbose=True,
    )

    statistical_enricher_agent = Agent(
        role="Statistical Enricher",
        goal="Interpret statistical metrics and highlight outliers.",
        backstory="You contextualise raw numbers for decision-making.",
        verbose=True,
    )

    # Our flagship forecasting analyst with TFT integration
    forecasting_analyst = create_enhanced_forecasting_analyst(
        evaluation_start_date=evaluation_start_date,
    )

    historical_trend_analyst = Agent(
        role="Historical Trend Analyst",
        goal="Compare current setups with past analogues to classify pattern alignment.",
        backstory="You find historical precedents for today's price action.",
        verbose=True,
    )

    summary_agent = Agent(
        role="Analysis Summary Agent",
        goal="Combine outputs from Analysis Agents into a unified report for the Timing Crew.",
        backstory="You gather and streamline findings.",
        verbose=True,
    )

    return [
        backtesting_agent,
        statistical_enricher_agent,
        forecasting_analyst,
        historical_trend_analyst,
        summary_agent,
    ] 