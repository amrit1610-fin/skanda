import os
from .base_agent import ReActAgent

class UserProxy(ReActAgent):
    def __init__(self):
        skill_path = os.path.join(os.path.dirname(__file__), '..', '.skills', 'user_proxy', 'system_prompt.md')
        super().__init__("UserProxy", skill_path)

    def announce_strategy_change(self, new_strategy):
        """Announce strategy change to the team."""
        self.think(f"Strategy has changed to '{new_strategy}'. Announcing to team.")
        return self.act("announce_change", {"new_strategy": new_strategy})
