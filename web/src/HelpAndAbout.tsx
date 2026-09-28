import { useEffect, useRef } from "react";
import authorAvatar from "./assets/king-a23-avatar.jpg";
import { DISPLAY_NAME } from "./constants";
import { useSendShortcut } from "./useSendShortcut";

export function HelpAndAbout() {
  const { sendLabel, newlineLabel } = useSendShortcut();
  const helpRef = useRef<HTMLDetailsElement>(null);
  const aboutRef = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    // Desktop menu links open the relevant explanation directly.
    function revealSection() {
      const section = window.location.hash === "#help" ? helpRef.current
        : window.location.hash === "#about" ? aboutRef.current : null;
      if (!section) return;
      section.open = true;
      section.querySelector("summary")?.focus({ preventScroll: true });
      section.scrollIntoView({ block: "start" });
    }
    const frame = requestAnimationFrame(revealSection);
    window.addEventListener("hashchange", revealSection);
    window.addEventListener("popstate", revealSection);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("hashchange", revealSection);
      window.removeEventListener("popstate", revealSection);
    };
  }, []);

  return <section className="settings-section settings-help" aria-labelledby="help-title">
    <h2 id="help-title">帮助与关于</h2>
    <details ref={helpRef} id="help" className="settings-details settings-guide">
      <summary>使用说明</summary>
      <div className="help-content">
        <h3>从今天开始</h3>
        <ol className="help-steps">
          <li>在「今天」写下一件想做的事，按回车添加。</li>
          <li>做完后勾选。点击标题可修改，更多操作在「···」里。</li>
          <li>误删时，点击页面底部的「撤销」；提示在 3 秒后自动消失。</li>
        </ol>

        <h3>事情放在哪里？</h3>
        <dl>
          <dt>计划 · 今天要推进的事</dt>
          <dd>未完成的计划会在第二天回到「待办」，由你决定何时再做。</dd>
          <dt>待办 · 以后再做的事</dt>
          <dd>先收下来，需要时加入今天。目标日期只是参考，不会自动安排。</dd>
          <dt>零碎事项 · 只属于当天的小事</dt>
          <dd>不会带到明天，未完成的事项也会留在当天历史中。</dd>
          <dt>定期事项 · 每天或每周重复的事</dt>
          <dd>勾选一次只完成当天的事项。暂停后不再生成新事项，可随时恢复；停止后不能恢复。</dd>
        </dl>
        <p className="settings-caption">可以切换日期查看历史，过去的日期只读。日期按北京时间（Asia/Shanghai）计算。</p>

        <h3>让计划助手搭把手</h3>
        <p>先在设置的「计划助手」中连接工具并检测环境，再打开右上角的「计划助手」，写下要添加或调整的内容。</p>
        <dl>
          <dt>暂停，再继续</dt>
          <dd>点击「暂停」挂起本机执行。不修改指令，点击「继续执行」即可从暂停处继续；已发出的远端请求可能仍在执行。</dd>
          <dt>调整指令</dt>
          <dd>暂停后直接编辑输入框，点击「按新指令继续」。已有改动会保留，助手会读取当前计划，开始新的执行。</dd>
          <dt>停止本次</dt>
          <dd>结束执行，保留已有改动。收起面板不会停止助手；退出应用会结束执行，下次打开不能接着原进程继续。</dd>
        </dl>

        <h3>备份与换电脑</h3>
        <p>在「数据与备份」中点击「立即备份」，展开备份列表后点击「下载」。在新电脑选择这个备份文件，再确认恢复即可。</p>
        <p className="settings-caption">恢复前会先备份现有数据。若助手正在执行或暂停，请先停止本次执行。助手连接与主题需要另行设置。</p>

        <h3>常用快捷键</h3>
        <dl className="help-shortcuts">
          <div><dt><kbd>⌘ N</kbd></dt><dd>快速新增事项</dd></div>
          <div><dt><kbd>Enter</kbd></dt><dd>添加事项</dd></div>
          <div><dt><kbd>{sendLabel}</kbd></dt><dd>发送助手指令（可在「快捷键」中更改）</dd></div>
          <div><dt><kbd>{newlineLabel}</kbd></dt><dd>助手指令换行</dd></div>
          <div><dt><kbd>⌘ ,</kbd></dt><dd>打开设置（桌面版）</dd></div>
          <div><dt><kbd>⌘ 1 / 2 / 3</kbd></dt><dd>今天 / 待办 / 定期事项（桌面版）</dd></div>
        </dl>
      </div>
    </details>

    <details ref={aboutRef} id="about" className="settings-details settings-about">
      <summary>关于 {DISPLAY_NAME} 与作者</summary>
      <div className="help-content">
        <div className="about-product"><h3>{DISPLAY_NAME}</h3><span className="settings-caption">版本 {__APP_VERSION__}</span></div>
        <p className="muted">一款保存在本机的简洁日计划软件。记下要做的事，把注意力留给今天。</p>
        <div className="about-author">
          <a href="https://github.com/King-A23" target="_blank" rel="noreferrer" aria-label="打开 Yuchen An 的 GitHub 主页">
            <img src={authorAvatar} width={64} height={64} alt="King-A23 的 GitHub 头像" />
          </a>
          <div><h3>Yuchen An</h3><p className="settings-caption">作者 · @King-A23</p>
            <a href="https://github.com/King-A23" target="_blank" rel="noreferrer">GitHub 主页 ↗</a></div>
        </div>
        <p className="settings-caption">事项和备份保存在本机，目前不提供云同步。手动记录无需联网；使用计划助手时，指令和计划上下文会交给所选工具及其模型服务。</p>
      </div>
    </details>
  </section>;
}
