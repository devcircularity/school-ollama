// services/api.ts - Fixed version that keeps users signed in
import axios from 'axios'

// Single API instance for all backend calls
export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL,
  timeout: 20000,
})

// Attach auth headers automatically
function getToken() {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('token')
}

function getSchoolId() {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('active_school_id')
}

api.interceptors.request.use((config) => {
  const token = getToken()
  const schoolId = getSchoolId()
  
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`
  }
  if (schoolId) {
    config.headers['X-School-ID'] = schoolId
  }
  
  return config
})

// Updated response interceptor - only handle specific cases
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Only log specific errors, don't automatically logout
    if (error.response?.status === 401) {
      console.warn('Unauthorized request - token may be expired')
      // Don't automatically logout - let the application handle this
      // The AuthContext should handle token validation and user logout decisions
    }
    
    // Log other errors for debugging
    if (error.response?.status >= 500) {
      console.error('Server error:', error.response.status)
    }
    
    return Promise.reject(error)
  }
)