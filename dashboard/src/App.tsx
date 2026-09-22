import { Route, BrowserRouter, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import DiscoveryPage from "./pages/DiscoveryPage";
import EscalationsPage from "./pages/EscalationsPage";
import RegistryPage from "./pages/RegistryPage";
import ReplayPage from "./pages/ReplayPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<RegistryPage />} />
          <Route path="/capabilities/:capabilityId" element={<RegistryPage />} />
          <Route path="/discovery" element={<DiscoveryPage />} />
          <Route path="/replay" element={<ReplayPage />} />
          <Route path="/escalations" element={<EscalationsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
