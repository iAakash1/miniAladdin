import time
from datetime import datetime
from crewai import Process

from .crews import build_postmortem_crew, build_analysis_crew


def main():
    """Execute Postmortem Crew followed by Analysis Crew with TFT integration."""

    # -------------------------------------------------------------------
    # 1. POSTMORTEM CREW
    # -------------------------------------------------------------------
    headlines_placeholder = "Sample delisted company headlines go here..."  # <-- Replace with real data
    postmortem_crew = build_postmortem_crew(headlines=headlines_placeholder)

    print("\nRunning Postmortem Crew...\n")
    postmortem_results = postmortem_crew.execute_sync()
    print("\nPostmortem Crew finished.\n")

    time.sleep(5)  # Small pause between crews

    # -------------------------------------------------------------------
    # 2. ANALYSIS CREW (includes TFT forecasting analyst)
    # -------------------------------------------------------------------
    evaluation_start_date = (datetime.now()).strftime("%Y-%m-%d")
    analysis_crew = build_analysis_crew(evaluation_start_date=evaluation_start_date)

    print("\nRunning Analysis Crew with TFT integration...\n")
    analysis_results = analysis_crew.execute_sync()
    print("\nAnalysis Crew finished.\n")


if __name__ == "__main__":
    main() 