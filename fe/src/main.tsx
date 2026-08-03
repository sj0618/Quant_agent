import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
// Tailwind first, legacy sheet second: un-migrated screens keep winning on conflicts.
import "./styles/tailwind.css";
import "./styles/global.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
