// app/page.tsx - Single root page that handles both public and authenticated users
'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'

export default function RootPage() {
  const router = useRouter()
  const { isAuthenticated, isLoading, active_school_id } = useAuth()

  useEffect(() => {
    if (isLoading) return // Wait for auth check

    if (isAuthenticated) {
      // Authenticated users go to workspace (which redirects to /chat/new)
      if (active_school_id) {
        router.replace('/chat/new')
      } else {
        router.replace('/onboarding/school')
      }
    } else {
      // Unauthenticated users go to public chat
      router.replace('/public')
    }
  }, [isAuthenticated, isLoading, active_school_id, router])

  // Show loading while determining where to redirect
  return (
    <div className="h-screen flex items-center justify-center">
      <div className="text-center">
        <div className="text-2xl font-semibold mb-2">
          {isLoading ? 'Loading...' : 'Redirecting...'}
        </div>
        <div className="text-neutral-600 dark:text-neutral-400">
          {isLoading ? 'Checking authentication...' : 'Taking you to the right place...'}
        </div>
      </div>
    </div>
  )
}