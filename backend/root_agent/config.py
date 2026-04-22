import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

def configure_genai():
    """Configures the Generative AI model."""
    # The project and location are sourced from the environment
    # when using Vertex AI transport.
    genai.configure(transport="vertexai")
    return genai

# Configure the model on import
llm = configure_genai()
