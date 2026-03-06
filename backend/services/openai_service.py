import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

def ask_gpt(system_prompt: str, user_message: str, json_mode: bool = False) -> str:
    """
    Single reusable function all agents use.
    Identical interface to our previous Azure version — nothing else changes.
    """
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.3,
        max_tokens=2000,
        **kwargs
    )
    return response.choices[0].message.content