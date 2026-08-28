import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import ErrorBanner from "@/components/ErrorBanner";
import { FullPageSpinner } from "@/components/Spinner";
import { wsUrl } from "@/lib/api";
import { vms } from "@/lib/resources";

type ConnState = "idle" | "connecting" | "open" | "closed" | "error";

/**
 * Opens the real console relay (backend ConsoleConsumer ->
 * AgentConsumer -> agent's VNC pipe, section 21) and proves the pipe is
 * live by counting received frames. This build does not include a
 * client-side VNC framebuffer renderer (noVNC) -- see
 * frontend/README.md's suggested next step -- so this shows connection
 * health rather than pretending to render a screen it can't.
 */
export default function ConsoleTab({ vmUuid, vmStatus }: { vmUuid: string; vmStatus: string }) {
  const consoleQuery = useQuery({ queryKey: ["console", vmUuid], queryFn: () => vms.console(vmUuid), enabled: vmStatus === "RUNNING" });
  const [state, setState] = useState<ConnState>("idle");
  const [frameCount, setFrameCount] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!consoleQuery.data) return undefined;

    setState("connecting");
    setFrameCount(0);
    const socket = new WebSocket(wsUrl(consoleQuery.data.websocket_url));
    socket.binaryType = "arraybuffer";
    socketRef.current = socket;

    socket.onopen = () => setState("open");
    socket.onmessage = () => setFrameCount((n) => n + 1);
    socket.onerror = () => setState("error");
    socket.onclose = () => setState("closed");

    return () => socket.close();
  }, [consoleQuery.data]);

  if (vmStatus !== "RUNNING") {
    return <p className="py-8 text-center text-xs text-surface-500">Start the VM to open a console session.</p>;
  }

  if (consoleQuery.isLoading) return <FullPageSpinner />;

  return (
    <div className="space-y-3">
      <ErrorBanner error={consoleQuery.error} />
      <div className="card space-y-3 p-4">
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${state === "open" ? "bg-status-online" : state === "connecting" ? "bg-status-warning" : state === "error" ? "bg-status-error" : "bg-surface-600"}`}
          />
          <span className="text-sm text-surface-200">
            {state === "open" && "Connected to console relay"}
            {state === "connecting" && "Connecting..."}
            {state === "error" && "Connection error"}
            {state === "closed" && "Disconnected"}
            {state === "idle" && "Not connected"}
          </span>
          {state === "open" && <span className="text-xs text-surface-500">{frameCount} frame(s) received</span>}
        </div>

        <div className="flex aspect-video items-center justify-center rounded-md border border-dashed border-surface-700 bg-surface-950 text-center">
          <p className="max-w-sm px-4 text-xs text-surface-500">
            The relay to the agent's VNC socket is live (see the connection status above), but this build doesn't
            include a client-side VNC framebuffer renderer. Wire in noVNC against this same WebSocket
            (base64-decoded binary frames -- see agent/nodepilot_agent/console.py) to render the actual screen here.
          </p>
        </div>
      </div>
    </div>
  );
}
