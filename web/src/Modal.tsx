import { useEffect, useRef, type ReactNode } from "react";

export function Modal({ label, onClose, children, className = "" }: {
  label: string; onClose: () => void; children: ReactNode; className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current!;
    dialog.showModal();
    dialog.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    return () => { dialog.close(); if (previous?.isConnected) previous.focus(); };
  }, []);
  return <dialog ref={ref} className={`planner-modal ${className}`} aria-label={label}
    onCancel={(event) => { event.preventDefault(); closeRef.current(); }}>
    {children}
  </dialog>;
}
