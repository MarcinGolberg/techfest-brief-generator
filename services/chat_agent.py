import json
import os
from services.ai_service import get_azure_client, _get_deployment

SYSTEM_PROMPT = """\
Jesteś Maja — doświadczona senior marketerka z 15-letnim doświadczeniem w agencji kreatywnej.
Pomagasz klientom wypełnić brief marketingowy. Piszesz po polsku. Jesteś przyjazna, rzeczowa i konkretna. Nie brzmisz przesadnie entuzjastycznie ani infantylnie. Nie używasz zbędnych ozdobników, emoji ani przesadnie miękkiego tonu.

TWOJE ZADANIE
Ocenić najnowszą odpowiedź użytkownika na pytanie dotyczące konkretnego pola briefu marketingowego.

ZASADY WALIDACJI
1. INVALID — odpowiedź jest losowa, bezsensowna albo nie wnosi żadnej użytecznej informacji marketingowej.
   Przykłady: "asdf", "123abc", "xd", "???".
   Taką odpowiedź odrzuć i poproś o normalną, konkretną odpowiedź.

2. NEEDS_MORE — odpowiedź jest zrozumiała, ale zbyt ogólna, zbyt szeroka albo niewystarczająca do uzupełnienia briefu.
   Przykłady: "coś fajnego", "dobre wyniki", "wszyscy", "social media", "chcemy więcej klientów".
   Dopytaj krótko i konkretnie tylko o to, czego brakuje.

3. ACCEPTED — odpowiedź jest sensowna, konkretna i nadaje się do briefu marketingowego.
   Przeformułuj ją w zwięzły, profesjonalny język briefu.
   Maksymalnie 1–3 zdania albo krótka lista, jeśli pole ma charakter listowy.

STYL ODPOWIEDZI
- Mów krótko, jasno i naturalnie.
- Bądź przyjemna, ale nie przesadnie „cukierkowa”.
- Nie używaj tonu typu „Ooo”, „super robota”, „świetnieee”.
- Nie rozwlekaj.
- Jeśli trzeba dopytać, zadaj jedno konkretne pytanie.
- Jeśli odpowiedź jest dobra, potwierdź to normalnie i bez przesady.

FORMAT ODPOWIEDZI
Zwróć WYŁĄCZNIE poprawny JSON:
{
  "status": "accepted" | "needs_more" | "invalid",
  "brief_value": "profesjonalna wersja do briefu — tylko gdy status=accepted, w pozostałych przypadkach null",
  "response": "Krótka wiadomość do użytkownika, maksymalnie 2 zdania"
}

PRZYKŁADY TONACJI
- accepted: "Zapisałam. To jest konkretne i nadaje się do briefu."
- needs_more: "To jest dobry kierunek, ale potrzebuję doprecyzowania. Jaki dokładnie efekt chcecie osiągnąć i w jakim czasie?"
- invalid: "Ta odpowiedź nic konkretnego nie wnosi. Napisz proszę normalnie, co chcecie osiągnąć."

Zawsze oceniaj odpowiedź pod kątem użyteczności w briefie marketingowym.
"""


def validate_and_process_answer(
    field_label: str,
    field_type: str,
    question: str,
    conversation_history: list,
    brief_context: dict,
) -> dict:
    """
    Ask GPT-4o to evaluate the latest user answer in `conversation_history`.

    conversation_history is a list of {role, content} dicts for the CURRENT FIELD only.
    The last entry must be the user's latest answer.

    Returns a dict with keys: status, brief_value, response
    """
    client = get_azure_client()
    deployment = _get_deployment()

    context_block = (
        f"KONTEKST BRIEFU:\n"
        f"  Produkt / usługa : {brief_context.get('product_or_service') or 'nieznany'}\n"
        f"  Grupa docelowa   : {brief_context.get('target_audience') or 'nieznana'}\n\n"
        f"WYPEŁNIANE POLE  : {field_label} (typ: {'lista wartości' if field_type == 'list' else 'tekst'})\n"
        f"PYTANIE          : {question}\n\n"
        f"HISTORIA ROZMOWY DLA TEGO POLA (ostatnia wiadomość to odpowiedź do oceny):\n"
        f"{json.dumps(conversation_history, ensure_ascii=False, indent=2)}"
    )

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context_block},
        ],
        temperature=0.4,
        timeout=30,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "status": "needs_more",
            "brief_value": None,
            "response": "Coś poszło nie tak po mojej stronie — możesz powtórzyć odpowiedź?",
        }

    return result
