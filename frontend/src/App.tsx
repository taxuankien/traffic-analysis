import { Outlet } from 'react-router-dom';
import { TopBar } from './components/layout/TopBar';
import { Footer } from './components/layout/Footer';

export default function App() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <TopBar />
      <main style={{ flex: 1, overflow: 'auto' }}>
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
