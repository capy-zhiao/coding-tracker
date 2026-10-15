// Route table: which URL renders which page.
// ":number" is a dynamic segment — /solve/994 passes "994" to the Solve page.
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { useAuth } from './lib/auth'
import Login from './pages/Login'
import Today from './pages/Today'
import Solve from './pages/Solve'
import Drills from './pages/Drills'
import Drill from './pages/Drill'
import Patterns from './pages/Patterns'
import Mock from './pages/Mock'
import Stats from './pages/Stats'

export default function App() {
  const { status } = useAuth()
  if (status === 'loading') return null
  if (status === 'signed-out') return <Login />

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Today />} />
        <Route path="/solve/:number" element={<Solve />} />
        <Route path="/drill" element={<Drills />} />
        <Route path="/drill/:number" element={<Drill />} />
        {/* The library now lives in Stats, under each chapter */}
        <Route path="/problems" element={<Navigate to="/stats" replace />} />
        <Route path="/patterns" element={<Patterns />} />
        <Route path="/mock" element={<Mock />} />
        <Route path="/stats" element={<Stats />} />
      </Routes>
    </Layout>
  )
}
