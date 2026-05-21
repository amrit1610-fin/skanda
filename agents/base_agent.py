import os
import re
import json
import importlib
from datetime import datetime
import anthropic

class ReActAgent:
    def __init__(self, name, skill_path=None):
        self.name = name
        self.system_prompt = ""
        self.active_tool = None
        self.model_name = "claude-3-5-sonnet-20241022"
        
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            self.llm_client = anthropic.Anthropic(api_key=api_key)
        else:
            self.llm_client = None
            print(f"[{self.name}] Warning: ANTHROPIC_API_KEY not found in environment. LLM disabled.")
            
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
        # Prevent printing massive DataFrames to console, which causes Pandas/Regex to crash
        if isinstance(action_data, dict) and "ohlcv_data" in action_data:
            print(f"[{self.name}] Action: {action_name} | Data: <MarketData Payload Omitted>")
        else:
            # Safely truncate long strings so the terminal doesn't lag
            data_str = str(action_data)
            if len(data_str) > 200:
                data_str = data_str[:200] + " ... [TRUNCATED]"
            print(f"[{self.name}] Action: {action_name} | Data: {data_str}")
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
        except Exception as log_err:
            print(f"[{self.name}] WARNING: Failed to write to agent_stream.log: {log_err}")

    def evaluate(self, market_data: dict):
        """
        Gathers tool data, builds the context payload, and calls the Anthropic API
        for a decision, then safely parses the resulting JSON.
        """
        # 1. Gather local data/indicators via tools
        tool_results = self.enforce_tool_execution(market_data)

        if not self.llm_client:
            self.think("Evaluation aborted: Anthropic client not initialized (missing API key).")
            return None

        self.think("Sending data to Claude...")

        # 2. Construct the payload
        # Pandas DataFrames might be in market_data, so we provide a safe serializer fallback
        def safe_serialize(obj):
            if hasattr(obj, 'to_dict'):
                return obj.to_dict()
            if hasattr(obj, 'tolist'):
                return obj.tolist()
            return str(obj)

        payload_obj = {
            "market_data": market_data,
            "tool_results": tool_results
        }

        try:
            user_message = json.dumps(payload_obj, default=safe_serialize)
        except Exception as e:
            self.think(f"Warning: JSON serialization failed ({e}), converting payload to string.")
            user_message = str(payload_obj)

        # 3. Call the Claude API
        try:
            response = self.llm_client.messages.create(
                model=self.model_name,
                max_tokens=1024,
                system=self.system_prompt if self.system_prompt else "You are an autonomous agent.",
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )
            
            response_text = response.content[0].text
            self.think("Received response from Claude.")
            
            # 4. Safely parse JSON from the response text
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                json_str = match.group(0)
            else:
                json_str = response_text
                
            decision = json.loads(json_str)
            return decision

        except json.JSONDecodeError as e:
            self.think(f"Error parsing JSON from Claude response: {e}\nResponse was: {response_text}")
            return None
        except Exception as e:
            self.think(f"Error during Anthropic API call: {e}")
            return None