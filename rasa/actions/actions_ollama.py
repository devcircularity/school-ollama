"""
Custom Rasa Actions that leverage Ollama for intelligent responses
"""

from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, FollowupAction
import requests
import json
import logging

logger = logging.getLogger(__name__)


class ActionOllamaContextualHelp(Action):
    """
    Provides contextual help using Ollama based on conversation state
    """
    
    def name(self) -> Text:
        return "action_ollama_contextual_help"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        # Build context from current conversation
        context = self._build_context(tracker)
        
        # Generate contextual help with Ollama
        help_text = self._generate_help(context)
        
        dispatcher.utter_message(text=help_text)
        
        return []
    
    def _build_context(self, tracker: Tracker) -> Dict:
        """Extract relevant context from tracker"""
        
        return {
            "active_form": tracker.active_loop_name,
            "requested_slot": tracker.get_slot("requested_slot"),
            "filled_slots": {
                k: v for k, v in tracker.current_slot_values().items()
                if v is not None
            },
            "recent_intents": [
                event.get("name") 
                for event in tracker.events 
                if event.get("event") == "user" and event.get("parse_data", {}).get("intent")
            ][-3:],
            "conversation_length": len([
                e for e in tracker.events if e.get("event") == "user"
            ])
        }
    
    def _generate_help(self, context: Dict) -> str:
        """Use Ollama to generate contextual help"""
        
        prompt = f"""You are a helpful school management assistant. Based on the current conversation state, provide helpful guidance.

Context:
{json.dumps(context, indent=2)}

Provide a brief, friendly help message explaining:
1. What the user is currently doing
2. What information is still needed (if any)
3. What other things they can ask you to do

Keep it conversational and under 100 words."""

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2:latest",
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.3
                },
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()["response"].strip()
        
        except Exception as e:
            logger.error(f"Ollama help generation failed: {e}")
        
        # Fallback
        return "I can help you manage students, classes, academic years, fees, and guardians. What would you like to do?"


class ActionOllamaSmartCorrection(Action):
    """
    Uses Ollama to intelligently handle corrections and clarifications
    Example: "No, I meant student not guardian"
    """
    
    def name(self) -> Text:
        return "action_ollama_smart_correction"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        last_user_message = tracker.latest_message.get("text")
        conversation_history = self._get_recent_history(tracker)
        
        # Use Ollama to understand the correction
        correction = self._interpret_correction(
            last_user_message,
            conversation_history
        )
        
        if correction:
            dispatcher.utter_message(text=f"Got it! {correction['explanation']}")
            
            # Clear incorrect slots
            events = [SlotSet(slot, None) for slot in correction.get("clear_slots", [])]
            
            # Redirect to correct action
            if correction.get("followup_action"):
                events.append(FollowupAction(correction["followup_action"]))
            
            return events
        
        dispatcher.utter_message(text="I'm not sure what to correct. Could you be more specific?")
        return []
    
    def _get_recent_history(self, tracker: Tracker, n: int = 5) -> List[Dict]:
        """Get recent conversation turns"""
        
        history = []
        for event in tracker.events[-n*2:]:  # Get last n exchanges
            if event.get("event") == "user":
                history.append({
                    "type": "user",
                    "text": event.get("text"),
                    "intent": event.get("parse_data", {}).get("intent", {}).get("name")
                })
            elif event.get("event") == "bot":
                history.append({
                    "type": "bot",
                    "text": event.get("text")
                })
        
        return history
    
    def _interpret_correction(
        self,
        correction_text: str,
        history: List[Dict]
    ) -> Dict:
        """Use Ollama to understand what needs to be corrected"""
        
        history_str = "\n".join([
            f"{h['type'].upper()}: {h.get('text', h.get('intent', 'N/A'))}"
            for h in history
        ])
        
        prompt = f"""Analyze this correction in a school management conversation.

Conversation History:
{history_str}

User Correction: "{correction_text}"

Determine:
1. What did the user originally intend?
2. What slots/data should be cleared?
3. What action should follow?

Respond ONLY with JSON:
{{
  "explanation": "brief confirmation of understanding",
  "clear_slots": ["slot1", "slot2"],
  "followup_action": "action_name" or null
}}

JSON Response:"""

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2:latest",
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.2
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()["response"]
                # Parse JSON from response
                json_start = result.find("{")
                json_end = result.rfind("}") + 1
                
                if json_start >= 0 and json_end > json_start:
                    return json.loads(result[json_start:json_end])
        
        except Exception as e:
            logger.error(f"Correction interpretation failed: {e}")
        
        return None


class ActionOllamaSummarizeContext(Action):
    """
    Summarizes current conversation context for the user
    Useful for long sessions or resuming interrupted work
    """
    
    def name(self) -> Text:
        return "action_ollama_summarize_context"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        # Get all filled slots and recent actions
        filled_slots = {
            k: v for k, v in tracker.current_slot_values().items()
            if v is not None
        }
        
        recent_actions = [
            event.get("name")
            for event in tracker.events[-10:]
            if event.get("event") == "action"
        ]
        
        summary = self._generate_summary(filled_slots, recent_actions)
        
        dispatcher.utter_message(text=summary)
        
        return []
    
    def _generate_summary(
        self,
        slots: Dict,
        actions: List[str]
    ) -> str:
        """Generate a summary of current state"""
        
        prompt = f"""Summarize the current state of this school management conversation.

Current Information Collected:
{json.dumps(slots, indent=2)}

Recent Actions:
{', '.join(actions[-5:])}

Provide a brief, clear summary (2-3 sentences) of:
1. What's been done so far
2. What's in progress
3. What might be next

Be conversational and concise."""

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2:latest",
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.3
                },
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()["response"].strip()
        
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
        
        return "Here's where we are: " + ", ".join([
            f"{k}={v}" for k, v in list(slots.items())[:3]
        ])