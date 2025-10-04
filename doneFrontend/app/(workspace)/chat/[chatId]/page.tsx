// app/(workspace)/chat/[chatId]/page.tsx - Fixed to prevent unnecessary reloads
'use client'

import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { chatService, type ConversationDetail } from '@/services/chats'
import { useAuthGuard } from '@/hooks/useAuthGuard'
import { HeaderTitleBus } from '@/components/layout/HeaderBar'
import ChatWrapper from '@/components/chat/ChatWrapper'

export default function ChatDetail() {
  const { isAuthenticated } = useAuthGuard()
  const params = useParams<{ chatId: string }>()
  const router = useRouter()
  const chatId = params.chatId
  
  const [conversation, setConversation] = useState<ConversationDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Check if chatId is a valid UUID
  const isValidUUID = (str: string) => {
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
    return uuidRegex.test(str)
  }

  // Load conversation data from backend
  const loadConversation = useCallback(async () => {
    if (!chatId || chatId === 'new') {
      setLoading(false)
      setConversation(null)
      return
    }

    if (!isValidUUID(chatId)) {
      setLoading(false)
      setConversation(null)
      return
    }

    try {
      setLoading(true)
      setError(null)
      
      const conversationData = await chatService.getConversation(chatId)
      setConversation(conversationData)
      
    } catch (err: any) {
      console.error('Failed to load conversation:', err)
      
      if (err?.response?.status === 404) {
        router.replace('/chat/new')
        return
      } else if (err?.response?.status === 401 || err?.response?.status === 403) {
        router.replace('/public')        
      } else {
        setError('Failed to load conversation')
      }
    } finally {
      setLoading(false)
    }
  }, [chatId, router])

  useEffect(() => {
    if (isAuthenticated) {
      loadConversation()
    }
  }, [isAuthenticated, loadConversation])

  // Update header title when conversation changes
  useEffect(() => {
    const title = conversation?.title || 'New Chat'
    HeaderTitleBus.send({ 
      type: 'set', 
      title, 
      subtitle: 'Ask me anything about your school management' 
    })

    return () => {
      HeaderTitleBus.send({ type: 'clear' })
    }
  }, [conversation?.title])

  // Handle conversation creation (when user sends first message)
  const handleConversationCreated = useCallback((conversationId: string) => {
    console.log('New conversation created:', conversationId)
    
    // Broadcast update event for sidebar refresh
    const updateEvent = {
      type: 'conversation_created',
      conversationId,
      timestamp: Date.now()
    }
    localStorage.setItem('chat_update_event', JSON.stringify(updateEvent))
    
    setTimeout(() => {
      localStorage.removeItem('chat_update_event')
    }, 100)
  }, [])

  // Handle conversation updates (when messages are added)
  const handleConversationUpdated = useCallback((conversationId: string) => {
    console.log('Conversation updated:', conversationId)
    
    // FIXED: Only reload if it's NOT the current conversation
    // This prevents unnecessary reloads when user sends messages to current chat
    if (conversationId !== chatId) {
      loadConversation()
    }
    
    // Broadcast update event for sidebar refresh
    const updateEvent = {
      type: 'conversation_updated',
      conversationId,
      timestamp: Date.now()
    }
    localStorage.setItem('chat_update_event', JSON.stringify(updateEvent))
    
    setTimeout(() => {
      localStorage.removeItem('chat_update_event')
    }, 100)
  }, [chatId, loadConversation])

  // Listen for storage events from other tabs/components
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'chat_update_event' && e.newValue) {
        try {
          const updateEvent = JSON.parse(e.newValue)
          // Only reload if it's a different conversation or external update
          if (updateEvent.conversationId !== chatId) {
            loadConversation()
          }
        } catch (error) {
          console.error('Error parsing storage event:', error)
        }
      }
    }

    window.addEventListener('storage', handleStorageChange)
    return () => window.removeEventListener('storage', handleStorageChange)
  }, [chatId, loadConversation])

  if (!isAuthenticated) {
    return null
  }

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center px-4">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">Loading conversation...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center px-4">
        <div className="text-center max-w-sm">
          <p className="text-red-600 dark:text-red-400 mb-4 text-sm">{error}</p>
          <div className="flex flex-col gap-2 sm:flex-row sm:gap-3 justify-center">
            <button
              onClick={() => loadConversation()}
              className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
            >
              Retry
            </button>
            <button
              onClick={() => router.push('/chat/new')}
              className="px-4 py-2 bg-neutral-600 text-white rounded text-sm hover:bg-neutral-700"
            >
              New Chat
            </button>
          </div>
        </div>
      </div>
    )
  }

  // For new chats or existing conversations, use the ChatWrapper
  return (
    <div className="h-full flex flex-col overflow-hidden">
      {conversation ? (
        // Existing conversation
        <ChatWrapper
          conversationId={conversation.id}
          initialMessages={conversation.displayMessages}
          onConversationUpdated={handleConversationUpdated}
          className="h-full"
        />
      ) : (
        // New conversation
        <>
          {/* Welcome screen for new chats */}
          <div className="flex-1 flex items-center justify-center px-3 sm:px-6 overflow-y-auto">
            <div className="text-center py-6 sm:py-10 max-w-md mx-auto">
              <h3 className="text-base sm:text-lg font-medium text-neutral-900 dark:text-neutral-100 mb-2">
                Welcome to School Chat
              </h3>
              <p className="text-neutral-600 dark:text-neutral-400 mb-4 text-sm sm:text-base">
                I can help you manage students, classes, fees, and more. Try asking:
              </p>
              <div className="space-y-2 text-sm">
                <div className="bg-neutral-100 dark:bg-neutral-800 rounded-lg p-3 text-left">
                  "Show me school overview"
                </div>
                <div className="bg-neutral-100 dark:bg-neutral-800 rounded-lg p-3 text-left">
                  "List all students"
                </div>
                <div className="bg-neutral-100 dark:bg-neutral-800 rounded-lg p-3 text-left">
                  "Create class P4 East"
                </div>
              </div>
            </div>
          </div>
          
          {/* Chat wrapper for new conversations */}
          <div className="flex-none">
            <ChatWrapper
              onConversationCreated={handleConversationCreated}
              onConversationUpdated={handleConversationUpdated}
            />
          </div>
        </>
      )}
    </div>
  )
}