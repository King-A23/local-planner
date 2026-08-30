import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { DISPLAY_NAME } from "./constants";
import "./styles.css";

document.title = DISPLAY_NAME;

const root = document.getElementById("root");
if (!root) {
  throw new Error("missing #root");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
