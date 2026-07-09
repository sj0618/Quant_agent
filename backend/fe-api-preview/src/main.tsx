import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { DataSourcePanel } from "./components/common/DataSourcePanel";
import "./styles/global.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
    <DataSourcePanel />
  </StrictMode>,
);
