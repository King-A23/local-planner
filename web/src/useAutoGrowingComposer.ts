import { useCallback, useLayoutEffect, type RefObject } from "react";

/** Measure at the compact width first, so expanding never causes layout oscillation. */
export function useAutoGrowingComposer(
  formRef: RefObject<HTMLFormElement | null>,
  fieldRef: RefObject<HTMLTextAreaElement | null>,
) {
  const resize = useCallback(() => {
    const form = formRef.current;
    const field = fieldRef.current;
    if (!form || !field || !field.getClientRects().length) return;

    const formStyle = getComputedStyle(form);
    const fieldStyle = getComputedStyle(field);
    const controls = Array.from(form.querySelectorAll<HTMLElement>(".agent-pill-control"));
    const gaps = formStyle.gridTemplateColumns.split(" ").length - 1;
    const compactWidth = form.clientWidth - parseFloat(formStyle.paddingLeft) - parseFloat(formStyle.paddingRight)
      - controls.reduce((width, control) => width + control.offsetWidth, 0)
      - parseFloat(formStyle.columnGap) * gaps;
    const singleLineHeight = parseFloat(fieldStyle.lineHeight)
      + parseFloat(fieldStyle.paddingTop) + parseFloat(fieldStyle.paddingBottom);
    const minHeight = parseFloat(fieldStyle.minHeight);
    const maxHeight = parseFloat(fieldStyle.maxHeight);
    const scrollTop = field.scrollTop;

    // Use the textarea's own layout for CJK, emoji, pasted text and soft wrapping.
    field.style.width = `${Math.max(1, compactWidth)}px`;
    field.style.minHeight = "0";
    field.style.height = "0";
    field.style.overflowY = "hidden";
    form.dataset.multiline = String(field.value.includes("\n") || field.scrollHeight > Math.ceil(singleLineHeight) + 1);
    field.style.width = "";
    const contentHeight = field.scrollHeight;
    const height = Math.max(minHeight, Math.min(contentHeight, maxHeight));
    field.style.height = `${height}px`;
    field.style.minHeight = "";
    field.style.overflowY = contentHeight > height + 1 ? "auto" : "hidden";
    field.scrollTop = scrollTop;
  }, [formRef, fieldRef]);

  // Includes prompt changes, reopening, helper selection and running/paused layout.
  useLayoutEffect(resize);
  useLayoutEffect(() => {
    const form = formRef.current;
    if (!form) return;
    let width = form.clientWidth;
    const observer = new ResizeObserver(() => {
      if (form.clientWidth === width) return;
      width = form.clientWidth;
      resize();
    });
    observer.observe(form);
    window.addEventListener("resize", resize);
    return () => { observer.disconnect(); window.removeEventListener("resize", resize); };
  }, [formRef, resize]);
}
