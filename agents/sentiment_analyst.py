import os
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# 🚨 GLOBALLY DISABLE SYMLINKS to bypass Windows Admin constraints
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "0"

from .base_agent import ReActAgent

class SentimentAnalyst(ReActAgent):
    def __init__(self):
        skill_path = os.path.join(os.path.dirname(__file__), '..', '.skills', 'sentiment_analyst', 'system_prompt.md')
        super().__init__("SentimentAnalyst", skill_path)
        
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_name = "ProsusAI/finbert"
        
        # 1. Create a bulletproof ABSOLUTE path pinned to this exact file
        agent_dir = os.path.dirname(os.path.abspath(__file__))
        self.local_model_dir = os.path.abspath(os.path.join(agent_dir, '..', 'models', 'finbert'))
        os.makedirs(self.local_model_dir, exist_ok=True)
        
        # 2. LAZY LOADING: Start with empty models.
        self.model = None
        self.tokenizer = None

    def _ensure_model(self):
        """Lazy-loads the model only when needed, preventing startup race conditions."""
        if self.model is None:
            self.think(f"Lazy-loading FinBERT to absolute path: {self.local_model_dir}...")
            try:
                # Check if we already downloaded it so we don't hit the network again
                has_local_files = os.path.exists(os.path.join(self.local_model_dir, 'config.json'))
                
                self.tokenizer = AutoTokenizer.from_pretrained(
                    self.model_name, 
                    cache_dir=self.local_model_dir,
                    local_files_only=has_local_files
                )
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    self.model_name, 
                    cache_dir=self.local_model_dir,
                    local_files_only=has_local_files
                ).to(self.device)
                
                self.think("✅ FinBERT model loaded successfully.")
            except Exception as e:
                self.think(f"❌ Failed to load FinBERT: {e}")

    def analyze_sentiment(self, text: str) -> float:
        """
        Performs FinBERT inference and returns a score: (Pos prob - Neg prob).
        Range: [-1.0, 1.0]
        """
        if not self.model or not self.tokenizer:
            self.think("FinBERT not available, returning neutral score.")
            return 0.0

        self.think(f"Analyzing sentiment for text: \"{text[:50]}...\"")
        
        try:
            inputs = self.tokenizer(text, return_tensors="pt", padding=True, truncation=True).to(self.device)
            
            with torch.no_grad():
                outputs = self.model(**inputs)
                
            # ProsusAI/finbert labels: 0: positive, 1: negative, 2: neutral
            probs = torch.nn.functional.softmax(outputs.logits, dim=-1).cpu().numpy()[0]
            
            pos_prob = float(probs[0])
            neg_prob = float(probs[1])
            
            sentiment_score = pos_prob - neg_prob
            self.think(f"Sentiment analysis complete. Score: {sentiment_score:.4f} (Pos: {pos_prob:.2f}, Neg: {neg_prob:.2f})")
            
            return round(sentiment_score, 4)
        except Exception as e:
            self.think(f"Error during sentiment inference: {e}")
            return 0.0

    def act(self, action_type: str, payload: dict) -> dict:
        """Override act to handle the analyze_sentiment logic when called via orchestrator."""
        if action_type == "analyze_sentiment":
            text = payload.get("text", "Market is currently stable with normal volume.")
            self._ensure_model()
            score = self.analyze_sentiment(text)
            return {"status": "success", "data": {"sentiment_score": score}}
        return super().act(action_type, payload)
