import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

declare const __APP_VERSION__: string;
declare const __BUILD_ID__: string;

if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    const workerUrl = new URL("/sw.js", window.location.origin);
    workerUrl.searchParams.set("v", `${__APP_VERSION__}-${__BUILD_ID__}`);
    let reloading = false;

    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (reloading) return;
      reloading = true;
      window.location.reload();
    });

    navigator.serviceWorker.register(workerUrl, { scope: "./", updateViaCache: "none" })
      .then((registration) => {
        const checkForUpdate = () => {
          if (document.visibilityState === "visible") {
            registration.update().catch((error: unknown) =>
              console.error("Automatic app update check failed", error));
          }
        };
        checkForUpdate();
        window.setInterval(checkForUpdate, 60 * 60 * 1000);
        document.addEventListener("visibilitychange", checkForUpdate);
      })
      .catch((error: unknown) => console.error("Service worker registration failed", error));
  });
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>,
);
