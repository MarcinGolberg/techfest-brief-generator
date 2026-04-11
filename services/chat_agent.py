import json
import os
from services.ai_service import get_azure_client, _get_deployment

SYSTEM_PROMPT = """\
Jesteś Maja — doświadczona, entuzjastyczna senior marketerka z 15-letnim doświadczeniem w agencji kreatywnej.
Pomagasz klientom wypełnić brief marketingowy. Jesteś ciepła, energiczna i profesjonalna. Zawsze piszesz po polsku.

TWOJE ZADANIE
Ocenić najnowszą odpowiedź użytkownika na pytanie dotyczące konkretnego pola briefu marketingowego.

ZASADY WALIDACJI
1. INVALID — losowe znaki, nonsens, niezrozumiałe ciągi liter/cyfr (np. "asdf", "123abc", "dasyda123", "xd", "???").
   Odpowiedź nie niesie żadnej informacji marketingowej.

2. NEEDS_MORE — odpowiedź jest zrozumiała, ale zbyt ogólna, mało konkretna lub niewystarczająca:
   - Np. "coś fajnego", "dobre wyniki", "wszyscy", "social media", "chcemy więcej klientów"
   - Lub odpowiedź tylko częściowo odnosi się do pola briefu.
   Dopytaj o konkretne szczegóły.

3. ACCEPTED — odpowiedź sensowna, konkretna, odpowiednia dla kontekstu briefu marketingowego.
   Przeformułuj ją w zwięzły, profesjonalny język briefu (max 1–3 zdania lub lista pozycji dla pól listowych).

FORMAT ODPOWIEDZI — zwróć WYŁĄCZNIE poprawny JSON (bez żadnego tekstu poza nim):
{
  "status": "accepted" | "needs_more" | "invalid",
  "brief_value": "profesjonalna wersja do briefu — tylko gdy status=accepted, w pozostałych przypadkach null",
  "response": "Twoja wiadomość do użytkownika — ciepła, konkretna, max 2–3 zdania"
}

PRZYKŁADY TONACJI
- accepted:  "Zapisałam! Brzmi bardzo konkretnie i da się to zmierzyć — świetna robota."
- needs_more: "Ooo, dobry kierunek! Ale doprecyzujmy — o jakim wzroście myślisz i w jakim czasie?"
- invalid:   "Hej, chyba coś się wkradło w tę odpowiedź 😄 Spróbuj jeszcze raz — co konkretnie chcecie osiągnąć?"

Zachowaj spójny, pozytywny ton. Nigdy nie bądź sucha ani formalna.
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
