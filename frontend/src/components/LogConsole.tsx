import type { RefObject } from "react";
import type { LogLine } from "../types";


interface LogConsoleProps {
  activeConsoleTab: "logs" | "preview";
  setActiveConsoleTab: (tab: "logs" | "preview") => void;
  consoleContainerRef: RefObject<HTMLDivElement | null>;
  logs: LogLine[];
}

export function LogConsole({
  activeConsoleTab,
  setActiveConsoleTab,
  consoleContainerRef,
  logs
}: LogConsoleProps) {
  return (
    <div style={{ marginTop: "12px" }}>
      <div className="tab-container" style={{ borderBottom: "none", marginBottom: "8px" }}>
        <div className="segmented-tabs-container">
          <button
            className={`segmented-tab-btn ${activeConsoleTab === "logs" ? "active" : ""}`}
            onClick={() => setActiveConsoleTab("logs")}
          >
            Nhật ký xử lý (Logs)
          </button>
        </div>
      </div>
      <div className="console-output" ref={consoleContainerRef}>
        {logs.map((log, idx) => (
          <div key={idx} className={`log-line log-${log.type}`}>
            [{log.time}] {log.text}
          </div>
        ))}
      </div>
    </div>
  );
}
export default LogConsole;
