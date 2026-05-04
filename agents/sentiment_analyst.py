import os
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from .base_agent import ReActAgent

class SentimentAnalyst(ReActAgent):
    def __init__(self):
        skill_path = os.path.join(os.path.dirname(__file__), '..', '.skills', 'sentiment_analyst', 'system_prompt.md')
        super().__init__("SentimentAnalyst", skill_path)
        
        self.think("Initializing FinBERT model for sentiment analysis")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.think(f"Using device: {self.device}")
        
        try:
            self.tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
            self.model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert").to(self.device)
            self.think("FinBERT model loaded successfully")
        except Exception as e:
            self.think(f"Failed to load FinBERT: {e}")
            self.model = None

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
            score = self.analyze_sentiment(text)
            return {"status": "success", "data": {"sentiment_score": score}}
        return super().act(action_type, payload)
