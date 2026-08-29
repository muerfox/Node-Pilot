import RFB from "@novnc/novnc";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import ErrorBanner from "@/components/ErrorBanner";
import { FullPageSpinner } from "@/components/Spinner";
import { wsUrl } from "@/lib/api";
import { vms } from "@/lib/resources";

type ConnState = "idle" | "connecting" | "connected" | "disconnected" | "error";

/**
 * Renders the VM's real graphical console (section 21) using noVNC's RFB
 * client against the existing backend relay: ConsoleConsumer <->
 * AgentConsumer <-> the agent's local proxy onto QEMU's VNC socket
 * (agent/nodepilot_agent/console.py). That relay already speaks raw
 * binary frames both ways (base64 only on the internal agent<->
 * controller hop, transparently), so RFB's own WebSocket-and-binary-
 * protocol expectations are met with no extra framing on this end.
 */
export default function ConsoleTab({ vmUuid, vmStatus }: { vmUuid: string; vmStatus: string }) {
  const consoleQuery = useQuery({ queryKey: ["console", vmUuid], queryFn: () => vms.console(vmUuid), enabled: vmStatus === "RUNNING" });
  const [state, setState] = useState<ConnState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const rfbRef = useRef<RFB | null>(null);

  useEffect(() => {
    if (!consoleQuery.data || !containerRef.current) return undefined;

    setState("connecting");
    setMessage(null);

    const rfb = new RFB(containerRef.current, wsUrl(consoleQuery.data.websocket_url), {});
    rfb.scaleViewport = true;
    rfb.showDotCursor = true;
    rfb.viewOnly = false;
    rfbRef.current = rfb;

    const onConnect = () => setState("connected");
    const onDisconnect = (event: CustomEvent<{ clean: boolean }>) => {
      setState("disconnected");
      if (!event.detail?.clean) setMessage("The console connection was lost unexpectedly.");
    };
    const onSecurityFailure = (event: CustomEvent<{ reason?: string }>) => {
      setState("error");
      setMessage(event.detail?.reason ?? "Console security negotiation failed.");
    };
    const onCredentialsRequired = () => {
      // QEMU consoles created via domain_xml.build_domain_xml have no
      // VNC password configured, so this shouldn't normally fire; if it
      // does, surface it rather than hanging silently.
      setState("error");
      setMessage("The VNC server is asking for credentials this console session doesn't have.");
    };

    rfb.addEventListener("connect", onConnect);
    rfb.addEventListener("disconnect", onDisconnect as EventListener);
    rfb.addEventListener("securityfailure", onSecurityFailure as EventListener);
    rfb.addEventListener("credentialsrequired", onCredentialsRequired);

    return () => {
      rfb.removeEventListener("connect", onConnect);
      rfb.removeEventListener("disconnect", onDisconnect as EventListener);
      rfb.removeEventListener("securityfailure", onSecurityFailure as EventListener);
      rfb.removeEventListener("credentialsrequired", onCredentialsRequired);
      rfb.disconnect();
      rfbRef.current = null;
    };
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
            className={`h-2 w-2 rounded-full ${
              state === "connected" ? "bg-status-online" : state === "connecting" ? "bg-status-warning" : state === "error" ? "bg-status-error" : "bg-surface-600"
            }`}
          />
          <span className="text-sm text-surface-200">
            {state === "connected" && "Connected"}
            {state === "connecting" && "Connecting..."}
            {state === "error" && "Connection error"}
            {state === "disconnected" && "Disconnected"}
            {state === "idle" && "Not connected"}
          </span>
          {message && <span className="text-xs text-status-error">{message}</span>}
        </div>

        <div
          ref={containerRef}
          className="aspect-video w-full overflow-hidden rounded-md border border-surface-700 bg-black [&>canvas]:h-full [&>canvas]:w-full [&>div]:h-full [&>div]:w-full"
        />
      </div>
    </div>
  );
}
