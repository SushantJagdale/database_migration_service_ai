from google.adk.agents import LlmAgent
import os
import subprocess
from dotenv import load_dotenv

load_dotenv()

def generate_final_report(user_prompt: str) -> str:
    """
    Runs the script to generate the final HTML report from the markdown files.
    This should be run after the MySQL and PostgreSQL agents have completed.
    """
    print("--- HTML Generator Agent: Generating Final HTML Report ---")
    try:
        # The script is located in the parent 'root_agent' directory
        script_path = os.path.join(os.path.dirname(__file__), '..', 'report_generator.py')
        
        # Ensure the script is called with the correct python executable from the venv
        python_executable = os.path.join(os.getcwd(), 'venv', 'bin', 'python')

        if not os.path.exists(python_executable):
            python_executable = 'python3' # Fallback if venv python not found

        result = subprocess.run(
            [python_executable, script_path],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"--- HTML Report Generation Successful --- \n{result.stdout}")
        return "artifacts/final_report.html"
    except subprocess.CalledProcessError as e:
        error_message = f"Failed to generate HTML report. Error: {e.stderr}"
        print(f"ERROR: {error_message}")
        return error_message
    except FileNotFoundError:
        error_message = "Error: The report_generator.py script was not found."
        print(f"ERROR: {error_message}")
        return error_message

# --- Agent Definition ---
report_generator_agent = LlmAgent(
    name="HtmlGeneratorAgent",
    model=os.getenv("MODEL"),
    instruction="""Your task is to generate the final HTML report.
    Call the `generate_final_report` tool, passing the user's original prompt.
    Your final output MUST be ONLY the file path returned by the tool, and nothing else.
    For example: `artifacts/final_report.html`
    """,
    description="Generates the final HTML report after other agents have created the markdown files.",
    tools=[generate_final_report],
)