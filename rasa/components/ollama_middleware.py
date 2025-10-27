"""
Rasa Middleware to integrate Ollama preprocessing
Compatible with Rasa 3.x
"""

from typing import Dict, Text, Any, List, Optional
import logging

# Rasa 3.x imports
from rasa.engine.graph import GraphComponent, ExecutionContext
from rasa.engine.recipes.default_recipe import DefaultV1Recipe
from rasa.engine.storage.resource import Resource
from rasa.engine.storage.storage import ModelStorage
from rasa.shared.nlu.training_data.message import Message
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.shared.nlu.constants import TEXT, INTENT, ENTITIES

# Import preprocessor - use try/except for flexible imports
try:
    from components.ollama_preprocessor import get_preprocessor
except ImportError:
    from ollama_preprocessor import get_preprocessor

logger = logging.getLogger(__name__)


@DefaultV1Recipe.register(
    DefaultV1Recipe.ComponentType.MESSAGE_FEATURIZER, is_trainable=False
)
class OllamaEnhancedNLU(GraphComponent):
    """
    Custom Rasa 3.x NLU Component that uses Ollama for preprocessing
    
    This component:
    1. Takes user text
    2. Preprocesses with Ollama
    3. Enriches the message with normalized text and entities
    4. Lets Rasa's pipeline continue with enhanced input
    """
    
    @staticmethod
    def get_default_config() -> Dict[Text, Any]:
        """Returns default config for the component."""
        return {
            "use_ollama": True,
            "fallback_to_original": True,
            "confidence_threshold": 0.7
        }
    
    def __init__(
        self,
        config: Dict[Text, Any],
        model_storage: ModelStorage,
        resource: Resource,
    ) -> None:
        """Initialize the component."""
        self._config = {**self.get_default_config(), **config}
        self.preprocessor = get_preprocessor()
        
        logger.info(
            f"Initialized OllamaEnhancedNLU with use_ollama={self._config['use_ollama']}"
        )
    
    @classmethod
    def create(
        cls,
        config: Dict[Text, Any],
        model_storage: ModelStorage,
        resource: Resource,
        execution_context: ExecutionContext,
    ) -> "OllamaEnhancedNLU":
        """Creates a new component (see interface)."""
        return cls(config, model_storage, resource)
    
    def train(self, training_data: TrainingData) -> Resource:
        """
        Training phase - we don't train Ollama, just pass through
        """
        # Nothing to train - Ollama is used at runtime
        return self._resource
    
    def process_training_data(
        self, training_data: TrainingData
    ) -> TrainingData:
        """Process training data - passthrough for Ollama."""
        return training_data
    
    def process(self, messages: List[Message]) -> List[Message]:
        """
        Process incoming messages with Ollama preprocessing
        """
        
        if not self._config.get("use_ollama", True):
            return messages
        
        for message in messages:
            self._process_single_message(message)
        
        return messages
    
    def _process_single_message(self, message: Message) -> None:
        """Process a single message with Ollama."""
        
        original_text = message.get(TEXT)
        
        if not original_text:
            return
        
        try:
            # Get current context (if available from tracker)
            context = self._extract_context(message)
            
            # Preprocess with Ollama
            result = self.preprocessor.preprocess(original_text, context)
            
            # Update message with normalized text
            normalized_text = result.get("normalized_text", original_text)
            
            # If confidence is high enough, use normalized text
            confidence = result.get("confidence", 0.0)
            threshold = self._config.get("confidence_threshold", 0.7)
            
            if confidence >= threshold:
                message.set(TEXT, normalized_text)
                logger.debug(
                    f"Ollama normalized: '{original_text}' → '{normalized_text}' "
                    f"(confidence: {confidence:.2f})"
                )
            else:
                logger.debug(
                    f"Confidence {confidence:.2f} below threshold {threshold}, "
                    f"keeping original text"
                )
            
            # Add Ollama entities to message metadata
            ollama_entities = result.get("entities", [])
            if ollama_entities:
                # Store in message data for potential use
                message.set("ollama_entities", ollama_entities, add_to_output=True)
                
                # Optionally inject high-confidence entities
                self._inject_entities(message, ollama_entities, confidence)
            
            # Store suggested intent for fallback scenarios
            suggested_intent = result.get("suggested_intent")
            if suggested_intent:
                message.set("ollama_intent", suggested_intent, add_to_output=True)
            
        except Exception as e:
            logger.error(f"Ollama preprocessing error: {e}", exc_info=True)
            if not self._config.get("fallback_to_original", True):
                raise
    
    def _extract_context(self, message: Message) -> Dict:
        """Extract relevant context from message."""
        
        context = {}
        
        # Get any metadata from message
        metadata = message.data.get("metadata", {})
        if metadata:
            context["metadata"] = metadata
        
        return context
    
    def _inject_entities(
        self,
        message: Message,
        ollama_entities: List[Dict],
        confidence: float
    ) -> None:
        """
        Inject high-confidence Ollama entities into message
        Only if confidence is very high to avoid conflicts
        """
        
        # Only inject if very confident
        if confidence < 0.85:
            return
        
        existing_entities = message.get(ENTITIES, [])
        
        # Add Ollama entities that don't conflict
        for entity in ollama_entities:
            # Check if entity already exists
            entity_type = entity.get("entity")
            entity_value = entity.get("value")
            
            # Don't duplicate existing entities
            if not any(e.get("entity") == entity_type for e in existing_entities):
                existing_entities.append({
                    "entity": entity_type,
                    "value": entity_value,
                    "confidence": confidence,
                    "extractor": "ollama"
                })
        
        message.set(ENTITIES, existing_entities)


# For backwards compatibility with older documentation
Component = OllamaEnhancedNLU


# Alternative: Function-based middleware for endpoints
def preprocess_message_with_ollama(message: str, tracker_state: Dict = None) -> str:
    """
    Standalone function to preprocess messages
    Can be called from custom actions or endpoints
    """
    preprocessor = get_preprocessor()
    
    context = {}
    if tracker_state:
        context = {
            "slots": tracker_state.get("slots", {}),
            "active_form": tracker_state.get("active_loop", {}).get("name")
        }
    
    result = preprocessor.preprocess(message, context)
    return result.get("normalized_text", message)