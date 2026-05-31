import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import HomePage from './pages/HomePage'
import LoginPage from './pages/LoginPage'
import ModelConfigPage from './pages/ModelConfigPage'
import KnowledgePage from './pages/KnowledgePage'
import ImagePage from './pages/ImagePage'
import TagPage from './pages/TagPage'
import MemoryPage from './pages/MemoryPage'
import RequireAuth from './components/RequireAuth'

// 阶段1：登录页 + 路由守卫；主布局需登录后访问
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <MainLayout />
            </RequireAuth>
          }
        >
          <Route index element={<HomePage />} />
          <Route path="knowledge" element={<KnowledgePage />} />
          <Route path="images" element={<ImagePage />} />
          <Route path="memory" element={<MemoryPage />} />
          <Route path="tags" element={<TagPage />} />
          <Route path="settings/models" element={<ModelConfigPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
