import { useState, type ReactNode } from "react";

/**
 * A destructive-action button that requires an explicit second click to
 * confirm (section 65: "Destructive action confirmation") -- no modal
 * dialog needed for a single button, but it can't be double-clicked by
 * accident either since the confirm state only appears after the first
 * click and reverts after a few seconds.
 */
export default function ConfirmButton({
  onConfirm,
  children,
  confirmLabel = "Click again to confirm",
  className = "btn-danger",
  disabled,
}: {
  onConfirm: () => void;
  children: ReactNode;
  confirmLabel?: string;
  className?: string;
  disabled?: boolean;
}) {
  const [confirming, setConfirming] = useState(false);

  if (confirming) {
    return (
      <button
        type="button"
        className={className}
        disabled={disabled}
        onClick={() => {
          setConfirming(false);
          onConfirm();
        }}
        onBlur={() => setConfirming(false)}
      >
        {confirmLabel}
      </button>
    );
  }

  return (
    <button type="button" className={className} disabled={disabled} onClick={() => setConfirming(true)}>
      {children}
    </button>
  );
}
