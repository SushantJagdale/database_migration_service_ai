# from dotenv import load_dotenv
# load_dotenv()

from google.adk.agents import ParallelAgent, SequentialAgent
from .mysql.mysql_agent import mysql_dms_agent
from .postgres.postgres_agent import postgres_dms_agent
from .report.report_generator_agent import report_generator_agent


# A SequentialAgent to run the database checks sequentially.
db_checker_agent = SequentialAgent(
    name="DBCheckerAgent",
    description="Runs checks for both MySQL and PostgreSQL databases in parallel.",
    sub_agents=[mysql_dms_agent, postgres_dms_agent],
)

# The root_agent is now a SequentialAgent.
# It first runs the parallel (due to httpx.ConnectError updated Parallel Agent to Sequencial for time being) database checks, and then runs the HTML report generator.
root_agent = SequentialAgent(
    name="root_agent",
    description="A root agent that first runs database checks in parallel, and then generates a consolidated HTML report.",
    sub_agents=[db_checker_agent, report_generator_agent],
)
