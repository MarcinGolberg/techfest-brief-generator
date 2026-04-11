import json
import os
from services.ai_service import get_azure_client, _get_deployment

EDIT_SYSTEM_PROMPT = """\
Jesteś asystentem pomagającym edytować brief marketingowy na podstawie poleceń użytkownika w języku polskim.

Otrzymasz:
1. Aktualny brief (JSON)
2. Polecenie edycji od użytkownika

TWOJE ZADANIE:
- Zrozumieć, które pole lub pola briefu użytkownik chce zmienić
- Zastosować zmianę profesjonalnie i konkretnie
- Zwrócić wyłącznie zmienione pola oraz potwierdzenie po polsku

Dostępne pola briefu:
- campaign_goal: Cel kampanii (string)
- product_or_service: Produkt lub usługa (string)
- target_audience: Grupa docelowa (string)
- key_messages: Kluczowe komunikaty (list — tablica stringów)
- marketing_channels: Kanały marketingowe (list — tablica stringów)
- tone_of_voice: Ton komunikacji (string)
- kpis: KPI (list — tablica stringów)
- success_measurement: Ocena sukcesu (string)
- scope_of_work: Zakres działań (string)
- client_expectations: Oczekiwania klienta (string)

FORMAT ODPOWIEDZI — zwróć WYŁĄCZNIE poprawny JSON bez żadnego tekstu poza nim:
{
  "updated_fields": {
    "field_name": "nowa wartość (string lub lista stringów zależnie od pola)"
  },
  "response": "Krótkie potwierdzenie zmiany — ciepłe, konkretne, max 2 zdania po polsku"
}

Jeśli polecenie jest niejasne lub nie wiesz co zmienić, zwróć updated_fields jako {} i wyjaśnij w response co możesz zrobić.
"""


def edit_brief_with_prompt(brief: dict, edit_prompt: str) -> dict:
    """
    Process a natural-language edit prompt against the current brief.
    Returns { updated_fields: {field: value, ...}, response: str }
    """
    client = get_azure_client()
    deployment = _get_deployment()

    context = (
        f"AKTUALNY BRIEF:\n{json.dumps(brief, ensure_ascii=False, indent=2)}\n\n"
        f"POLECENIE EDYCJI:\n{edit_prompt}"
    )

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": EDIT_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        temperature=0.3,
        timeout=30,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "updated_fields": {},
            "response": "Nie udało mi się przetworzyć polecenia. Spróbuj sformułować je inaczej.",
        }
