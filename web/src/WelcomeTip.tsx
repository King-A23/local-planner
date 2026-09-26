import { useState } from "react";

export function WelcomeTip() {
  const [visible, setVisible] = useState(() => {
    try { return localStorage.getItem("planner_welcome_seen") !== "1"; } catch { return true; }
  });
  if (!visible) return null;
  return <section className="welcome-tip" aria-label="使用提示">
    <div><strong>先记下一件今天要做的事</strong>
      <p>回车添加，做完勾选。未完成的计划明天回到待办；零碎事项不会带到明天。</p></div>
    <button type="button" className="linkish" onClick={() => {
      try { localStorage.setItem("planner_welcome_seen", "1"); } catch { /* optional preference */ }
      setVisible(false);
    }}>知道了</button>
  </section>;
}
