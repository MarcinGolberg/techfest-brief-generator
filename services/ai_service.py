import os
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

def get_azure_client():
    endpoint = os.getenv("AZURE_LLM_ENDPOINT")
    api_key = os.getenv("AZURE_LLM_API_KEY")
    api_version = os.getenv("AZURE_LLM_API_VERSION")

    if not endpoint:
        raise ValueError("Missing AZURE_LLM_ENDPOINT")
    if not api_key:
        raise ValueError("Missing AZURE_LLM_API_KEY")
    if not api_version:
        raise ValueError("Missing AZURE_LLM_API_VERSION")

    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version
    )

def _get_deployment():
    deployment = os.getenv("AZURE_LLM_DEPLOYMENT")
    if not deployment:
        raise ValueError("Missing AZURE_LLM_DEPLOYMENT")
    return deployment

def extract_brief_from_text(input_text: str) -> str:
    client = get_azure_client()
    deployment = _get_deployment()

    with open("prompts/extract_brief.txt", "r", encoding="utf-8") as f:
        prompt_template = f.read()

    prompt = prompt_template.replace("{{input_text}}", input_text)

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {
                "role": "system",
                "content": "You extract structured marketing brief data."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0
    )

    return response.choices[0].message.content

def extract_structured_text(prompt: str) -> str:
    client = get_azure_client()
    deployment = _get_deployment()

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {
                "role": "system",
                "content": "You generate structured JSON outputs for marketing workflow."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2
    )

    return response.choices[0].message.content