import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./index.css";

// CONCEPT: the root. React's virtual DOM is injected into this one
// <div id="root">. Everything rendered by React lives under here; the
// rest of the page stays static. This is the ONLY place we touch the
// real DOM at startup.
ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);