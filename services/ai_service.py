import os
import requests
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()


# ==========================================
# 1. TEXT GENERATION (LLM - AZURE)
# ==========================================
def get_azure_client():
    endpoint = os.getenv("AZURE_LLM_ENDPOINT")
    api_key = os.getenv("AZURE_LLM_API_KEY")
    api_version = os.getenv("AZURE_LLM_API_VERSION")

    if not endpoint or not api_key or not api_version:
        raise ValueError("Missing Azure LLM credentials in environment variables.")

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
            {"role": "system", "content": "You extract structured marketing brief data."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        timeout=30,
    )

    return response.choices[0].message.content


def extract_structured_text(prompt: str) -> str:
    client = get_azure_client()
    deployment = _get_deployment()

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": "You generate structured JSON outputs for marketing workflow."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        timeout=30,
    )

    return response.choices[0].message.content


# ==========================================
# 2. IMAGE GENERATION (FLUX API)
# ==========================================
def generate_badge_image(prompt: str) -> str:
    """
    Calls an external Flux API to generate an image.
    Returns the URL of the generated image.
    """
    api_key = os.getenv("FLUX_API_KEY")
    endpoint = os.getenv("FLUX_API_ENDPOINT")

    if not api_key or not endpoint:
        print("Missing Flux API credentials.")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # NOTE: The exact payload structure depends on your provider (Fal.ai, Replicate, etc.)
    # This is a standard generic payload structure.
    payload = {
        "prompt": prompt,
        "image_size": "square",  # or specific dimensions like width/height
        "num_inference_steps": 28
    }

    try:
        response = requests.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()  # Raise an error if the request failed

        data = response.json()

        # NOTE: You will need to adjust this depending on how your specific provider formats their JSON response
        image_url = data.get("image_url") or data.get("images")[0].get("url")

        return image_url

    except Exception as e:
        print(f"Error generating Flux image: {e}")
        # Print the raw response if there's an error so you can debug what the provider sent back
        if 'response' in locals():
            print(response.text)
        return None