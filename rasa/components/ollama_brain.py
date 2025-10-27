"""
Ollama Conversation Brain
Full reasoning engine replacing Rasa NLU and forms.
Now with smart workflow routing for student & guardian creation.
"""
import requests
import json
import logging
import os
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class OllamaBrain:
    def __init__(self):
        self.model = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
        self.url = os.getenv("OLLAMA_URL", "http://0.0.0.0:11434")
        self.temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0.3"))
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", "45"))
        self.conversation_memory: List[Dict] = []

        logger.info(f"🧠 OllamaBrain initialized: model={self.model}, url={self.url}")

    # =====================================================================
    def process(self, user_message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Main processor"""
        prompt = self._build_prompt(user_message, context)
        try:
            response = self._call_ollama(prompt)
            result = self._parse_response(response)
            self._update_memory(user_message, result)
            return result
        except requests.exceptions.ConnectionError:
            logger.error("💡 Ollama connection failed — ensure `ollama serve` is running.")
            return self._fallback()
        except Exception as e:
            logger.error(f"Ollama processing error: {e}", exc_info=True)
            return self._fallback()

    # =====================================================================
    def _build_prompt(self, user_message: str, context: Dict[str, Any]) -> str:
        """Compose prompt with domain-specific rules + conversational memory."""
        active_form = context.get("active_form")
        slots = context.get("slots", {})
        history = self._format_history()
        recent = context.get("recent_actions", [])

        # --- Explicit intent-action mapping ---
        action_mapping = """
    **ACTION MAPPING RULES**
    - When user says 'create student', 'add student', 'register student' → action_create_student
    - When user says 'add guardian', 'register guardian' → action_add_guardian
    - When user says 'list students' or 'show students' → action_list_students
    - When user says 'create class' → action_create_class
    - When user says 'create academic year' → action_create_academic_year
    - When user says 'record payment' → action_record_payment
    - When user says 'get school info' → action_get_school_info
    If unsure, respond naturally and ask clarifying questions. Only trigger the action when all required slots are filled.
    """

        # --- Student rules ---
        student_rules = """
    **STUDENT CREATION WORKFLOW**
    Ask for these in order:
    1. student_name (must contain at least first + last name)
    - If only one word: ask for the full name
    2. admission_no
    - If user says “auto generate”, store as "AUTO"
    3. class_name
    Once you have all 3, trigger:
    {
    "response": "Got it! Creating student Joshua Mwangi in Grade 5.",
    "action": "action_create_student",
    "slots": {
        "student_name": "Joshua Mwangi",
        "admission_no": "AUTO",
        "class_name": "Grade 5"
    }
    }
    """

        # --- Guardian rules ---
        guardian_rules = """
    **GUARDIAN CREATION WORKFLOW**
    Ask for:
    1. guardian_name
    2. relationship
    3. phone
    4. email
    5. student_name (the child they belong to)
    Once all are available:
    {
    "response": "Adding guardian Jane Njeri (mother) for Joshua Mwangi.",
    "action": "action_add_guardian",
    "slots": {
        "guardian_name": "Jane Njeri",
        "relationship": "mother",
        "phone": "0712345678",
        "email": "jane@example.com",
        "student_name": "Joshua Mwangi"
    }
    }
    """

        # --- System prompt with examples ---
        system = f"""
    You are an intelligent School Management AI Assistant connected to Rasa.
    Your job: understand what the user wants, gather missing info conversationally, and trigger Rasa actions when ready.

    **Rules:**
    1. Always validate data (e.g., names must have first and last name)
    2. Ask step-by-step for missing info
    3. Only trigger an action when all required data is available
    4. Never output plain text — respond ONLY with JSON

    **Example outputs:**
    {{
    "response": "Sure, let's create a student. What is the student's full name?",
    "action": null,
    "slots": {{}}
    }}

    {{
    "response": "Got it! Creating student Joshua Mwangi in Grade 5.",
    "action": "action_create_student",
    "slots": {{
        "student_name": "Joshua Mwangi",
        "admission_no": "AUTO",
        "class_name": "Grade 5"
    }}
    }}

    {action_mapping}
    {student_rules}
    {guardian_rules}

    Context:
    Active Form: {active_form or 'None'}
    Recent Actions: {recent[-3:]}
    Slots: {json.dumps(slots, indent=2)}
    Conversation History:
    {history}

    User said: "{user_message}"

    Respond **only** in JSON format:
    {{
    "response": "your reply",
    "action": "action_name or null",
    "slots": {{}}
    }}
    """
        return system.strip()

    # =====================================================================
    def _call_ollama(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "temperature": self.temperature,
            "format": "json",
        }
        res = requests.post(f"{self.url}/api/generate", json=payload, timeout=self.timeout)
        res.raise_for_status()
        data = res.json()
        return data.get("response", "")

    # =====================================================================
    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Ensure structured JSON output with fallback safety."""
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`").replace("json", "").strip()
        try:
            start, end = text.find("{"), text.rfind("}") + 1
            obj = json.loads(text[start:end])
            obj.setdefault("response", "I’m not sure what to say.")
            obj.setdefault("action", None)
            obj.setdefault("slots", {})
            return obj
        except Exception as e:
            logger.warning(f"⚠️ Failed to parse JSON from Ollama: {e} — raw: {text[:180]}")
            return {"response": text[:200], "action": None, "slots": {}}

    # =====================================================================
    def _format_history(self, n: int = 4) -> str:
        if not self.conversation_memory:
            return "(no prior context)"
        last = self.conversation_memory[-n:]
        return "\n".join([f"User: {t['user']}\nAI: {t['ai_response']}" for t in last])

    def _update_memory(self, user_message: str, result: Dict):
        self.conversation_memory.append({
            "user": user_message,
            "ai_response": result.get("response", ""),
            "action": result.get("action")
        })
        self.conversation_memory = self.conversation_memory[-10:]

    # =====================================================================
    def _fallback(self):
        return {
            "response": "I'm having trouble connecting to my reasoning engine. Please try again in a moment.",
            "action": None,
            "slots": {}
        }


# Singleton accessor
_brain = None
def get_brain():
    global _brain
    if not _brain:
        _brain = OllamaBrain()
    return _brain