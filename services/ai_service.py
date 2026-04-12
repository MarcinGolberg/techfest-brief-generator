import base64
import json
import os
from urllib.request import Request, urlopen
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


def _get_image_deployment():
    deployment = os.getenv("AZURE_IMAGE_DEPLOYMENT")
    if not deployment:
        raise ValueError("Missing AZURE_IMAGE_DEPLOYMENT")
    return deployment


def _extract_bytes_from_image_response(payload: dict) -> bytes:
    if not isinstance(payload, dict):
        raise ValueError("Niepoprawna odpowiedź modelu obrazu.")

    direct_b64 = payload.get("b64_json") or payload.get("image")
    if isinstance(direct_b64, str) and direct_b64.strip():
        try:
            return base64.b64decode(direct_b64)
        except Exception:
            pass

    if isinstance(payload.get("data"), list) and payload["data"]:
        item = payload["data"][0] or {}
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            with urlopen(item["url"]) as handle:
                return handle.read()

    if isinstance(payload.get("images"), list) and payload["images"]:
        item = payload["images"][0] or {}
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            with urlopen(item["url"]) as handle:
                return handle.read()

    if payload.get("url"):
        with urlopen(payload["url"]) as handle:
            return handle.read()

    raise ValueError(f"Nie udało się odczytać danych obrazu z odpowiedzi: {payload}")


def _generate_flux_image_bytes(prompt: str, size: str = "1024x1024", negative_prompt: str | None = None) -> bytes:
    endpoint = os.getenv("FLUX_API_ENDPOINT")
    api_key = os.getenv("FLUX_API_KEY") or os.getenv("AZURE_LLM_API_KEY")
    deployment = _get_image_deployment()

    if not endpoint:
        raise ValueError("Missing FLUX_API_ENDPOINT")
    if not api_key:
        raise ValueError("Missing FLUX_API_KEY")

    try:
        width_str, height_str = size.lower().split("x", 1)
        width = int(width_str)
        height = int(height_str)
    except Exception as exc:
        raise ValueError(f"Niepoprawny rozmiar obrazu '{size}'. Oczekiwano formatu np. 1024x1024.") from exc

    payload = {
        "model": deployment,
        "prompt": prompt,
        "width": width,
        "height": height,
        "output_format": "png",
        "num_images": 1,
    }
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt

    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    with urlopen(request) as response:
        response_payload = json.loads(response.read().decode("utf-8"))

    return _extract_bytes_from_image_response(response_payload)


def get_embedding_client():
    """Return an AzureOpenAI client for embeddings.

    Prefers AZURE_EMBEDDING_ENDPOINT / AZURE_EMBEDDING_API_KEY if set so
    organisations that host embeddings on a separate Azure resource can
    configure it independently.  Falls back to the LLM credentials.
    """
    endpoint = os.getenv("AZURE_EMBEDDING_ENDPOINT") or os.getenv("AZURE_LLM_ENDPOINT")
    api_key = os.getenv("AZURE_EMBEDDING_API_KEY") or os.getenv("AZURE_LLM_API_KEY")
    api_version = os.getenv("AZURE_LLM_API_VERSION")
    if not endpoint or not api_key or not api_version:
        raise ValueError(
            "Missing embedding credentials. Set AZURE_EMBEDDING_ENDPOINT (or AZURE_LLM_ENDPOINT), "
            "AZURE_EMBEDDING_API_KEY (or AZURE_LLM_API_KEY), and AZURE_LLM_API_VERSION."
        )
    return AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)


def get_embedding(text: str) -> list:
    """Return the embedding vector for *text* using the configured Azure deployment.

    Set AZURE_EMBEDDING_DEPLOYMENT to the name of your embedding deployment
    (e.g. ``text-embedding-3-large``).  Falls back to ``text-embedding-3-large``
    if the variable is absent.
    """
    client = get_embedding_client()
    deployment = os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")
    response = client.embeddings.create(model=deployment, input=text)
    return response.data[0].embedding


def strip_code_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ``` or ``` ... ```) from an LLM response."""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()
    return cleaned


def generate_image_bytes(prompt: str, size: str = "1024x1024", negative_prompt: str | None = None) -> bytes:
    if os.getenv("FLUX_API_ENDPOINT"):
        return _generate_flux_image_bytes(prompt=prompt, size=size, negative_prompt=negative_prompt)

    client = get_azure_client()
    deployment = _get_image_deployment()

    try:
        response = client.images.generate(
            model=deployment,
            prompt=prompt,
            size=size,
            n=1,
        )
    except Exception as exc:
        message = str(exc)
        if "Missing required parameter: 'messages'" in message:
            raise ValueError(
                "Błąd wywołania Azure OpenAI Image API. "
                "Jeśli używasz FLUX.2-pro albo FLUX.2-flex, ustaw FLUX_API_ENDPOINT i FLUX_API_KEY, "
                "bo te modele trzeba wywoływać przez provider-specific BFL API, a nie przez client.images.generate(...). "
                "Image API przez Azure OpenAI działa dla modeli takich jak FLUX-1.1-pro, FLUX.1-Kontext-pro, gpt-image-1 lub gpt-image-1.5."
            ) from exc
        raise

    if not response.data:
        raise ValueError("Model obrazu nie zwrócił żadnych danych.")

    image = response.data[0]
    image_b64 = getattr(image, "b64_json", None)
    if image_b64:
        return base64.b64decode(image_b64)

    image_url = getattr(image, "url", None)
    if image_url:
        with urlopen(image_url) as handle:
            return handle.read()

    raise ValueError("Nie udało się odczytać danych obrazu z odpowiedzi modelu.")
