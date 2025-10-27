from rasa_sdk import Action
from rasa_sdk.events import SlotSet

class ActionEndOllamaConversation(Action):
    def name(self):
        return "action_end_ollama_conversation"

    def run(self, dispatcher, tracker, domain):
        dispatcher.utter_message("✅ Done! You can now start another task.")
        return [
            SlotSet("ollama_conversation_active", False),
            SlotSet("ollama_workflow_type", None)
        ]