import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { RedirectIfSignedIn, RequireAuth } from '@/components/RouteGuards'
import { AuthProvider } from '@/lib/auth'
import ChatLayout from '@/pages/chat/ChatLayout'
import ChatThread from '@/pages/chat/ChatThread'
import NewChat from '@/pages/chat/NewChat'
import SignIn from '@/pages/SignIn'
import SignUp from '@/pages/SignUp'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route
            path="/sign-in"
            element={
              <RedirectIfSignedIn>
                <SignIn />
              </RedirectIfSignedIn>
            }
          />
          <Route
            path="/sign-up"
            element={
              <RedirectIfSignedIn>
                <SignUp />
              </RedirectIfSignedIn>
            }
          />
          <Route
            path="/chats"
            element={
              <RequireAuth>
                <ChatLayout />
              </RequireAuth>
            }
          >
            <Route index element={<NewChat />} />
            <Route path=":threadId" element={<ChatThread />} />
          </Route>
          <Route path="/" element={<Navigate to="/chats" replace />} />
          <Route path="*" element={<Navigate to="/chats" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
