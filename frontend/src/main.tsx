import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initRipple } from "./lib/ripple";
import "./index.css";

initRipple();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
