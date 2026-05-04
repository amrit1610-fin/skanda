import os
import re
import json
import importlib
from datetime import datetime

class ReActAgent:
    def __init__(self, name, skill_path=None):
        self.name = name
        self.system_prompt = ""
        self.active_tool = None
        if skill_path:
            self.load_skills(skill_path)

    def load_skills(self, skill_path):
        """Loads markdown instructions and checks for active python tools."""
        if os.path.exists(skill_path):
            with open(skill_path, 'r', encoding='utf-8') as f:
                self.system_prompt = f.read()
            self.think(f"Successfully loaded skills from {skill_path}")
            self._parse_and_load_tool()
        else:
            self.think(f"Skill file not found at {skill_path}. Operating without specific instructions.")

    def _parse_and_load_tool(self):
        """Parses the YAML frontmatter to find and load a requested python tool."""
        if not self.system_prompt:
            return
            
        # Match 'Uses Tool: module.path::function_name'
        match = re.search(r"Uses Tool:\s*(.+)::(.+)", self.system_prompt)
        if match:
            module_name = match.group(1).strip()
            function_name = match.group(2).strip()
            self.think(f"Parsed tool requirement: Module '{module_name}', Function '{function_name}'")
            
            try:
                module = importlib.import_module(module_name)
                self.active_tool = getattr(module, function_name)
                self.think(f"Successfully registered python tool '{function_name}' from '{module_name}'")
            except Exception as e:
                self.think(f"Failed to load python tool: {e}")
                self.active_tool = None
        else:
            self.think("No 'Uses Tool' directive found in skill file.")
            self.active_tool = None

    def enforce_tool_execution(self, payload):
        """Ensures the agent calls its loaded tool to get fresh data/indicators before reasoning."""
        if self.active_tool:
            self.think("Executing required tool to gather data and indicators...")
            try:
                # Pass either the entire payload or just the 'data' DataFrame if that's what the tool expects
                tool_input = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
                if tool_input is None:
                    self.think("Warning: Payload did not contain a 'data' key for the tool. Executing with full payload.")
                    tool_input = payload
                
                tool_result = self.active_tool(tool_input)
                self.think("Tool execution complete. Extracted new indicators.")
                return tool_result
            except Exception as e:
                self.think(f"Error executing tool: {e}")
                return None
        return None

    def think(self, thought_text):
        """Logs the internal reasoning process of the agent."""
        print(f"[{self.name}] Thinking: {thought_text}")
        self._log_stream("thought", thought_text)

    def act(self, action_name, action_data=None):
        """Executes an action and logs it."""
        print(f"[{self.name}] Action: {action_name} | Data: {action_data}")
        self._log_stream("action", f"Executed: {action_name}")
        return {"action": action_name, "data": action_data, "status": "executed"}

    def _log_stream(self, event_type, message):
        """Writes JSON events to a stream log file for the FastAPI websocket to broadcast."""
        log_file = os.path.join(os.path.dirname(__file__), '..', 'logs', 'agent_stream.log')
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        try:
            payload = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "agent": self.name,
                "type": event_type,
                "message": message
            }
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            pass
