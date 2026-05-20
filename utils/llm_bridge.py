import os
# Fix for the SSL_CERT_FILE error
if "SSL_CERT_FILE" in os.environ:
    del os.environ["SSL_CERT_FILE"]

from groq import Groq
# ... rest of your imports

import json
from groq import Groq
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# Get the key from the environment
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError("CRITICAL: GROQ_API_KEY not found in .env file")

client = Groq(api_key=api_key)

def get_cio_decision(market_data):
    """
    Sends market context to the Groq 'CIO' and gets a strategy recommendation.
    """
    try:
        # Dynamically find the project root based on this file's location
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        skill_path = os.path.join(base_dir, ".skills", "quant_analyst", "ensemble_manager.md")

        with open(skill_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()

        user_prompt = f"""
        Current Market Context:
        {json.dumps(market_data, indent=2)}
        
        CRITICAL CONSTRAINT: You must heavily weigh the 'macro_economist_bias' provided in the context. If the Macro Bias is Bearish, you are forbidden from Long trades, but you are ENCOURAGED to find high-probability Short Scalp opportunities using the 9/15 EMA soldier or Trendline Break.
        
        Based on your instructions, provide the strategy selection in JSON format:
        {{
            "selected_strategy": "strategy_name",
            "target_timeframe": "5m/15m/1h",
            "reasoning": "brief explanation"
        }}
        """

        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        print(f"[!] CIO Error: {e}")
        # Fallback logic if LLM fails
        return {"selected_strategy": "ema_8_30", "target_timeframe": "1h", "reasoning": "LLM Fallback"}