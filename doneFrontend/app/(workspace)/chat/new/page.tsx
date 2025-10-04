// app/(workspace)/chat/new/page.tsx - Fixed duplicate chat creation
'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthGuard } from '@/hooks/useAuthGuard'
import { HeaderTitleBus } from '@/components/layout/HeaderBar'
import ChatWrapper from '@/components/chat/ChatWrapper'

export default function NewChatPage() {
  const { isAuthenticated } = useAuthGuard()
  const router = useRouter()
  const [initialMessage, setInitialMessage] = useState<string | null>(null)
  const [initialContext, setInitialContext] = useState<any>(null)
  const [hasStartedChat, setHasStartedChat] = useState(false)

  // Check for stored initial message from workspace redirect
  useEffect(() => {
    const storedMessage = sessionStorage.getItem('chat-new-initial')
    const storedContext = sessionStorage.getItem('chat-new-context')
    
    if (storedMessage) {
      setInitialMessage(storedMessage)
      setHasStartedChat(true) // FIXED: Set this immediately to prevent showing landing page
      sessionStorage.removeItem('chat-new-initial')
    }
    
    if (storedContext) {
      try {
        setInitialContext(JSON.parse(storedContext))
        sessionStorage.removeItem('chat-new-context')
      } catch (error) {
        console.error('Failed to parse initial context:', error)
      }
    }
  }, [])

  // Update header title
  useEffect(() => {
    HeaderTitleBus.send({ 
      type: 'set', 
      title: 'New Chat', 
      subtitle: 'Ask me anything about your school management' 
    })

    return () => {
      HeaderTitleBus.send({ type: 'clear' })
    }
  }, [])

  // Handle conversation creation (redirect to the new conversation)
  const handleConversationCreated = useCallback((conversationId: string) => {
    console.log('New conversation created, redirecting to:', conversationId)
    router.replace(`/chat/${conversationId}`)
  }, [router])

  // Handle conversation updates
  const handleConversationUpdated = useCallback((conversationId: string) => {
    console.log('Conversation updated:', conversationId)
    
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

  const handleSuggestionClick = (prompt: string) => {
    console.log('Quick button clicked:', prompt)
    setInitialMessage(prompt)
    setHasStartedChat(true)
  }

  const QuickBtn = ({ label, prompt }: { label: string; prompt: string }) => (
    <button
      onClick={() => handleSuggestionClick(prompt)}
      className="rounded-xl bg-neutral-200/70 px-4 py-2 text-sm dark:bg-neutral-800/80 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition"
    >
      {label}
    </button>
  )

  if (!isAuthenticated) {
    return null
  }

  // If user has started chatting, show ONLY the chat interface
  // FIXED: Single ChatWrapper instance that handles everything
  if (hasStartedChat) {
    return (
      <div className="h-full flex flex-col overflow-hidden">
        <ChatWrapper
          onConversationCreated={handleConversationCreated}
          onConversationUpdated={handleConversationUpdated}
          className="h-full"
          initialMessage={initialMessage}
          initialContext={initialContext}
        />
      </div>
    )
  }

  // Show landing page design (only when NOT started chatting)
  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Welcome screen for new chats */}
      <div className="flex-1 flex items-center justify-center px-3 sm:px-6 overflow-y-auto">
        <div className="w-full max-w-3xl">
          {/* Logo */}
          <div className="text-center select-none mb-8">
            <div className="text-4xl sm:text-5xl lg:text-6xl xl:text-7xl font-semibold tracking-tight">
              <span className="text-neutral-900 dark:text-neutral-100">Olaji</span>{' '}
              <span style={{ color: 'var(--color-brand)' }}>Chat</span>
            </div>
            <div className="mt-3 text-base sm:text-lg text-neutral-600 dark:text-neutral-400">
              Your AI assistant for school management
            </div>
          </div>

          {/* Chat Input */}
          <div className="mx-auto max-w-2xl mb-6">
            <ChatWrapper
              onConversationCreated={handleConversationCreated}
              onConversationUpdated={handleConversationUpdated}
              placeholder="Ask me anything about school management..."
            />
          </div>

          {/* Shortcut "chips" */}
          <div className="flex flex-wrap items-center justify-center gap-2 max-w-2xl mx-auto">
            <QuickBtn label="How to create a class?" prompt="How do I create a new class?" />
            <QuickBtn label="How to enroll students?" prompt="How do I enroll a student?" />
            <QuickBtn label="How to manage fees?" prompt="How do I create invoices and manage fees?" />
            <QuickBtn label="How to track payments?" prompt="How do I record and track payments?" />
            <QuickBtn label="Show school overview" prompt="Show me an overview of the school" />
          </div>
        </div>
      </div>
    </div>
  )
}