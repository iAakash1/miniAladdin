# Developing a Multi-Agent Financial Forecasting System Using CrewAI

**Abstract**

This project proposes the development of a multi-agent system using the CrewAI framework to forecast short-term stock performance and construct optimized investment portfolios. The system, composed of specialized AI agents with distinct financial roles, will be evaluated over eight weeks by comparing its predictions and portfolio returns to actual market data. Introduction
Forecasting stock performance remains a difficult challenge due to market volatility and information overload. CrewAI, a Python framework for coordinating agents to collaborate, provides a unique approach to measuring financial performance. _This study asks: Can a CrewAI-based system predict short-term stock movements and create portfolios that outperform the market?_

**Background**

Traditional financial analysis relies on human expertise to interpret diverse data, such as SEC filings, technical indicators, and market sentiment. A multi-agent system can analyze financials similarly, but the question is, how effectively? CrewAI enables agents with specific goals, tasks, roles, and backstories to collaborate as financial analysts, making data-driven investment recommendations together.

**Methodology (8 Weeks)**

In Week 1, the system will be developed and tested. Approximately 20 agents will be created with defined roles such as earnings analysis, sentiment tracking, and macroeconomic scanning. Sources, such as 10-K reports, news articles, stock screeners, like Finviz, and price data APIs, will support data collection. Diversification is key to the success of a portfolio and will be maintained.
Starting Week 2, agents will evaluate each stock using metrics such as weekly return, volatility, Sharpe ratio, beta, alpha, drawdown, momentum, linear regression, correlation, and z-score. Each week, a new portfolio will be constructed based on agent recommendations, and predictions will be logged. A new separate evaluator agent will compare the previous week's forecast with actual results and provide feedback to the system. Adjustments will be made to agent behavior and inputs based on past performance.
Weeks 2–7 will follow this iterative cycle, emphasizing performance tracking and analytical refinement. Week 8 will focus on compiling a final report that summarizes findings, evaluates agents, and analyzes which indicators had the greatest impact.

**Expected Outcomes**

The final deliverable will be a functioning CrewAI system capable of producing evidence-backed investment recommendations. Its predictive accuracy will be benchmarked against real market data. The report will include a breakdown of agent performance, the credibility of data sources, and reflections on the possible practical applications. While returns may be conservative, the aim is to demonstrate that multi-agent collaboration can match or exceed traditional investment approaches.

**Conclusion**

This research explores the role of agents in financial forecasting. By leveraging CrewAI and credible financial data, the project seeks to build a system that not only automates but also enhances strategic investment decision-making. The results will offer insight into the viability of AI teams in applied financial research.

