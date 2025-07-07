from crewai import Task
from typing import List

# Simple placeholder tasks – structure mirrors notebook but trimmed for demonstration.

def create_postmortem_tasks(headlines: str, agents: List) -> List[Task]:
    """Create tasks for the Postmortem Crew given headlines text and agent list in matching order."""
    return [
        Task(
            description="Analyze delisted company headlines for systemic risks.",
            expected_output="Structured list of risk factors.",
            agent=agents[0],
        ),
        Task(
            description="Identify recurring failure signals from the headlines.",
            expected_output="Structured pattern analysis of failures.",
            agent=agents[1],
        ),
        Task(
            description="Detect confirmation bias in interpretations and propose mitigation checklist.",
            expected_output="Bias checklist.",
            agent=agents[2],
        ),
        Task(
            description="Assess overall sentiment tone in headlines and surface systemic risks.",
            expected_output="Sentiment and risk analysis report.",
            agent=agents[3],
        ),
        Task(
            description="Summarize all postmortem findings concisely for next crew.",
            expected_output="Comprehensive summary.",
            agent=agents[4],
        ),
    ]


def create_analysis_tasks(agents: List) -> List[Task]:
    """Create placeholder tasks for the Analysis Crew."""
    return [
        Task(
            description="Run a short-term backtest of candidate tickers with strict bias control.",
            expected_output="Table of risk/return metrics per ticker.",
            agent=agents[0],
        ),
        Task(
            description="Interpret statistical metrics and highlight outliers.",
            expected_output="Annotated metric interpretation.",
            agent=agents[1],
        ),
        Task(
            description="Generate 5-day direction predictions for all tickers using the integrated TFT model.",
            expected_output="Table of predicted directions and confidences.",
            agent=agents[2],
        ),
        Task(
            description="Compare recent moves with historical trend analogues.",
            expected_output="Trend alignment classification.",
            agent=agents[3],
        ),
        Task(
            description="Combine previous results into a unified analysis report for the Timing crew.",
            expected_output="Concise summary report.",
            agent=agents[4],
        ),
    ] 