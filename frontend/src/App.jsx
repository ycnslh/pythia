import { createContext } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useWebSocket } from "src/hooks/useWebSocket";
import Display from "src/views/Display";
import Feed from "src/views/Feed";
import en from "src/i18n/en";
import fr from "src/i18n/fr";

// Shared WebSocket context — single connection consumed by both views
export const WSContext = createContext({
  lastEvent: null,
  eventHistory: [],
  status: "connecting",
});

const I18N = { en, fr };
const lang = import.meta.env.VITE_LANGUAGE || "en";
const t = I18N[lang] ?? I18N.en;

export default function App() {
  const ws = useWebSocket();

  return (
    <WSContext.Provider value={ws}>
      <BrowserRouter>
        <Routes>
          <Route path="/display" element={<Display t={t} />} />
          <Route path="/feed" element={<Feed t={t} />} />
          <Route path="*" element={<Navigate to="/display" replace />} />
        </Routes>
      </BrowserRouter>
    </WSContext.Provider>
  );
}
