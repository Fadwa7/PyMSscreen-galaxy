import { BrowserRouter, Routes, Route } from 'react-router-dom';
import LandingPage from './components/LandingPage';
import ExtractionPage from './components/ExtractionPage';
import PlottingPage from './components/PlottingPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/extraction" element={<ExtractionPage />} />
        <Route path="/plotting" element={<PlottingPage />} />
      </Routes>
    </BrowserRouter>
  );
}
