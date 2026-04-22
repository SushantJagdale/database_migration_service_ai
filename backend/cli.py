import asyncio
import argparse
import os
import logging
import sys
from google.genai import types
from google.adk.runners import InMemoryRunner
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.code_executors.code_execution_utils import File
from root_agent.agent import root_agent

# --- Add this block to enable debug logging ---
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
# --- End of block ---

async def main(prompt: str):
    """
    Initializes the runner, creates a session, and runs the agent with the user's prompt.
    """
    runner = InMemoryRunner(
        agent=root_agent,
        app_name="db_discovery_app",
    )
    # if not os.getenv("GOOGLE_API_KEY"):
    #     raise ValueError("GOOGLE_API_KEY environment variable not set.")
    session = await runner.session_service.create_session(
        app_name="db_discovery_app", user_id="user"
    )

    print(f"--- Running Orchestrator with Prompt: '{prompt}' ---")

    content = types.Content(role='user', parts=[types.Part.from_text(text=prompt)])

    final_response = ""
    async for event in runner.run_async(
        user_id="user",
        session_id=session.id,
        new_message=content,
    ):
        if event.content and event.content.parts and event.content.parts[0].text:
            response_text = event.content.parts[0].text
            print(f"** {event.author}: {response_text}")
            final_response = response_text

    print("\n--- Orchestrator Finished ---")
    print("\nFinal Report:")
    print(final_response)

    # --- Add this block to generate the HTML report ---
    print("\n--- Generating Final HTML Report ---")
    from root_agent.html_report_generator import main as generate_html
    generate_html()
    print("--- HTML Report Generation Finished ---")
    # --- End of block ---

    # --- Add this block to register the report as an artifact ---
    if os.path.exists(".adk/artifacts/final_report.html"):
        with open(".adk/artifacts/final_report.html", "rb") as f:
            content = f.read()
        artifact_part = types.Part(
            inline_data=types.Blob(mime_type="text/html", data=content)
        )
        await runner.artifact_service.save_artifact(
            app_name="db_discovery_app",
            user_id=session.user_id if hasattr(session, 'user_id') else "user",
            session_id=session.id,
            filename="final_report.html",
            artifact=artifact_part,
        )
    # --- End of block ---

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run the root orchestrator agent.")
    parser.add_argument("prompt", type=str, help="The prompt to send to the agent.")
    args = parser.parse_args()
    asyncio.run(main(args.prompt))
