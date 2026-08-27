import { useCallback, useEffect, useState } from "react";
import { getHealth } from "../api/client.js";

export default function HealthIndicator() {
  const [state, setState] = useState("checking");

  const check = useCallback(async () => {
    setState("checking");
    try {
      const result = await getHealth();
      setState(result.ok ? "connected" : "unreachable");
    } catch {
      setState("unreachable");
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  return (
    <div className="health" data-testid="health-indicator" data-state={state}>
      <span className={`health-dot health-dot--${state}`} aria-hidden="true" />
      <span className="health-label">
        {state === "checking" && "Checking connection…"}
        {state === "connected" && "Connected to M8"}
        {state === "unreachable" && "M8 unreachable"}
      </span>
      <button type="button" className="ghost-button" onClick={check}>
        Retry connection
      </button>
    </div>
  );
}
