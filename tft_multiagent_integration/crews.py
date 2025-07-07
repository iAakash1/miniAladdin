from crewai import Crew, Process
from datetime import datetime
from typing import Optional

from .agents import get_postmortem_agents, get_analysis_agents
from .tasks import create_postmortem_tasks, create_analysis_tasks


# ---------------------------------------------------------------------------
# Convenience builders
# ---------------------------------------------------------------------------

def build_postmortem_crew(headlines: str) -> Crew:
    agents = get_postmortem_agents()
    tasks = create_postmortem_tasks(headlines=headlines, agents=agents)
    return Crew(agents=agents, tasks=tasks, process=Process.sequential)


def build_analysis_crew(
    evaluation_start_date: Optional[str] = None,
) -> Crew:
    if evaluation_start_date is None:
        evaluation_start_date = datetime.now().strftime("%Y-%m-%d")

    agents = get_analysis_agents(evaluation_start_date=evaluation_start_date)
    tasks = create_analysis_tasks(agents=agents)
    return Crew(agents=agents, tasks=tasks, process=Process.sequential) 