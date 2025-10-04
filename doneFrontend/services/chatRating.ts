// services/chatRating.ts - Updated for RESTful message rating endpoints

import { api } from './api'

export interface MessageRating {
  messageId: string
  conversationId: string
  rating: 1 | -1 | null
  userId: string
  createdAt: string
  updatedAt: string
}

export class ChatRatingService {
  /**
   * Rate a specific message within a conversation
   * Uses the RESTful endpoint: POST /api/chat/conversations/{conversation_id}/messages/{message_id}/rate
   */
  async rateMessage(messageId: string, rating: 1 | -1 | null): Promise<void> {
    try {
      // We need to extract conversation ID from the message
      // Since our frontend tracks this, we'll need to pass it or derive it
      const conversationId = this.extractConversationIdFromContext(messageId)
      
      if (!conversationId) {
        throw new Error('Cannot rate message: conversation ID not found')
      }

      await api.post(`/api/chat/conversations/${conversationId}/messages/${messageId}/rate`, {
        rating
      })
      
      console.log(`Message ${messageId} rated with ${rating}`)
    } catch (error: any) {
      console.error('Failed to rate message:', error)
      
      // Provide user-friendly error messages
      if (error.response?.status === 404) {
        throw new Error('Message not found')
      } else if (error.response?.status === 403) {
        throw new Error('You do not have permission to rate this message')
      } else if (error.response?.status === 400) {
        throw new Error(error.response.data?.detail || 'Invalid rating value')
      } else {
        throw new Error('Failed to submit rating. Please try again.')
      }
    }
  }

  /**
   * Rate a message with known conversation ID
   * This is the preferred method when conversation ID is available
   */
  async rateMessageInConversation(conversationId: string, messageId: string, rating: 1 | -1 | null): Promise<void> {
    try {
      await api.post(`/api/chat/conversations/${conversationId}/messages/${messageId}/rate`, {
        rating
      })
      
      console.log(`Message ${messageId} in conversation ${conversationId} rated with ${rating}`)
    } catch (error: any) {
      console.error('Failed to rate message:', error)
      
      if (error.response?.status === 404) {
        throw new Error('Message or conversation not found')
      } else if (error.response?.status === 403) {
        throw new Error('You do not have permission to rate this message')
      } else if (error.response?.status === 400) {
        throw new Error(error.response.data?.detail || 'Invalid rating value')
      } else {
        throw new Error('Failed to submit rating. Please try again.')
      }
    }
  }

  /**
   * Preload ratings for multiple messages
   * This method would need to be implemented on the backend
   * For now, we'll simulate it by making individual calls
   */
  async preloadRatings(messageIds: string[]): Promise<Record<string, number>> {
    try {
      // TODO: Implement batch endpoint on backend
      // For now, return empty object to avoid errors
      console.log('Preloading ratings for messages:', messageIds.length)
      return {}
    } catch (error) {
      console.error('Failed to preload ratings:', error)
      return {}
    }
  }

  /**
   * Get rating for a specific message
   * This would require the backend to provide a GET endpoint
   */
  async getMessageRating(conversationId: string, messageId: string): Promise<number | null> {
    try {
      // TODO: Implement GET endpoint on backend
      // GET /api/chat/conversations/{conversation_id}/messages/{message_id}/rating
      console.warn('Getting individual message rating not implemented on backend yet')
      return null
    } catch (error) {
      console.error('Failed to get message rating:', error)
      return null
    }
  }

  /**
   * Extract conversation ID from current context
   * This is a helper method that tries to determine the conversation ID
   * from the current page context or message data
   */
  private extractConversationIdFromContext(messageId: string): string | null {
    try {
      // Try to get from URL path
      const path = window.location.pathname
      const match = path.match(/\/chat\/([^\/]+)/)
      
      if (match && match[1] !== 'new') {
        return match[1]
      }
      
      // Try to get from localStorage or other context
      const currentConversation = localStorage.getItem('current_conversation_id')
      if (currentConversation) {
        return currentConversation
      }
      
      console.warn('Could not extract conversation ID for message:', messageId)
      return null
    } catch (error) {
      console.error('Error extracting conversation ID:', error)
      return null
    }
  }

  /**
   * Set current conversation ID in context
   * This helps the rating service know which conversation we're in
   */
  setCurrentConversation(conversationId: string): void {
    localStorage.setItem('current_conversation_id', conversationId)
  }

  /**
   * Clear current conversation context
   */
  clearCurrentConversation(): void {
    localStorage.removeItem('current_conversation_id')
  }
}

// Export singleton instance
export const chatRatingService = new ChatRatingService()