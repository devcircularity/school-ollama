// contexts/AuthContext.tsx - Fixed with better token validation
'use client'
import React, { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/services/api'

type AuthState = { 
  token: string | null
  active_school_id: string | null
  isLoading: boolean
  user: any | null
}

type AuthContextType = AuthState & {
  login: (data: { token: string; school_id?: string }) => Promise<void>
  logout: () => void
  setSchoolId: (schoolId: string) => void
  isAuthenticated: boolean
  validateToken: () => Promise<boolean>
}

const AuthCtx = createContext<AuthContextType>({
  token: null,
  active_school_id: null,
  isLoading: true,
  user: null,
  login: async () => {},
  logout: () => {},
  setSchoolId: () => {},
  isAuthenticated: false,
  validateToken: async () => false,
})

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ 
    token: null, 
    active_school_id: null,
    isLoading: true,
    user: null
  })
  const router = useRouter()

  // Validate token by checking with backend
  const validateToken = useCallback(async (): Promise<boolean> => {
    const token = localStorage.getItem('token')
    if (!token) {
      setState(prev => ({ ...prev, isLoading: false }))
      return false
    }

    try {
      console.log('Validating token...')
      const response = await api.get('/api/auth/me')
      
      if (response.data) {
        console.log('Token validated successfully')
        setState(prev => ({ 
          ...prev, 
          user: response.data,
          token: token,
          isLoading: false 
        }))
        return true
      }
    } catch (error: any) {
      console.error('Token validation failed:', error.response?.status, error.message)
      
      // Only clear token if it's definitively invalid (401/403)
      if (error.response?.status === 401 || error.response?.status === 403) {
        console.warn('Token is invalid, clearing authentication')
        localStorage.removeItem('token')
        localStorage.removeItem('active_school_id')
        setState({ 
          token: null, 
          active_school_id: null, 
          isLoading: false, 
          user: null 
        })
        return false
      }
      
      // For network errors or server errors, keep user logged in
      console.warn('Token validation failed due to network/server error, keeping user logged in')
      setState(prev => ({ 
        ...prev, 
        token: token,
        isLoading: false 
      }))
      return true
    }
    
    setState(prev => ({ ...prev, isLoading: false }))
    return false
  }, [])

  useEffect(() => {
    // Load auth state from localStorage
    const token = localStorage.getItem('token')
    const sid = localStorage.getItem('active_school_id')
    
    if (token) {
      console.log('Token found in localStorage, validating...')
      setState(prev => ({ 
        ...prev,
        token, 
        active_school_id: sid,
      }))
      
      // Validate token immediately
      validateToken().catch((error) => {
        console.error('Initial token validation failed:', error)
        setState(prev => ({ ...prev, isLoading: false }))
      })
    } else {
      console.log('No token found in localStorage')
      setState(prev => ({ ...prev, isLoading: false }))
    }
  }, [validateToken])

  const login = async (data: { token: string; school_id?: string }) => {
    console.log('Logging in with new token')
    localStorage.setItem('token', data.token)
    
    if (data.school_id) {
      localStorage.setItem('active_school_id', data.school_id)
    }
    
    setState(prev => ({ 
      ...prev, 
      token: data.token, 
      active_school_id: data.school_id || null,
      isLoading: false 
    }))
    
    // Validate and get user data
    await validateToken()
  }

  const logout = () => {
    console.log('Logging out user')
    localStorage.removeItem('token')
    localStorage.removeItem('active_school_id')
    setState({ 
      token: null, 
      active_school_id: null, 
      isLoading: false,
      user: null 
    })
    router.replace('/')
  }

  const setSchoolId = (schoolId: string) => {
    localStorage.setItem('active_school_id', schoolId)
    setState(prev => ({ ...prev, active_school_id: schoolId }))
  }

  const value: AuthContextType = {
    ...state,
    login,
    logout,
    setSchoolId,
    validateToken,
    isAuthenticated: !!state.token && !state.isLoading
  }

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}

export const useAuth = () => useContext(AuthCtx)