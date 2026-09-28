import authorAvatar from "./assets/king-a23-avatar.jpg";
import { DISPLAY_NAME } from "./constants";
import { useSendShortcut } from "./useSendShortcut";
import { ASSISTANT_EXAMPLES } from "./assistantExamples";

export function CommonShortcuts({ className = "settings-keyboard-list" }: { className?: string }) {
  return <dl className={className}>
    <div><dt>搜索事项</dt><dd><kbd>⌘ / Ctrl + K</kbd></dd></div>
    <div><dt>保存标题和备注</dt><dd><kbd>⌘ / Ctrl + Enter</kbd></dd></div>
    <div><dt>调整顺序（聚焦拖动柄）</dt><dd><kbd>⌥ / Alt + ↑ ↓</kbd></dd></div>
    <div><dt>打开事项菜单（聚焦事项）</dt><dd><kbd>Shift + F10</kbd></dd></div>
    <div><dt>选择菜单项</dt><dd><kbd>↑ ↓ / Home / End</kbd></dd></div>
    <div><dt>关闭当前菜单或窗口</dt><dd><kbd>Esc</kbd></dd></div>
    <div><dt>快速新增事项</dt><dd><kbd>⌘ / Ctrl + N</kbd></dd></div>
    <div><dt>打开设置（桌面版）</dt><dd><kbd>⌘ ,</kbd></dd></div>
    <div><dt>今天 / 待办 / 定期事项 / 目标（桌面版）</dt><dd><kbd>⌘ 1 / 2 / 3 / 4</kbd></dd></div>
  </dl>;
}

export function AssistantUsage() {
  return <>
    <p>可添加事项、搜索标题和备注、修改详情、改期、移回待办、完成或恢复、调整顺序，也能设置时间、参考日期、定期事项和目标行动。</p>
    <ul>{ASSISTANT_EXAMPLES.map((example) => <li key={example}>“{example}”</li>)}</ul>
    <p className="settings-caption">标题重复时请带上日期。过去的记录只读，零碎事项不能跨日移动。完成区的展开和折叠由你在界面操作。助手的询问和说明会直接显示在回执中；需要澄清时，补全原指令后重新发送，并核对返回的改动。</p>
  </>;
}

export function UsageGuide() {
  const { sendLabel, newlineLabel } = useSendShortcut();
  return <div className="help-content settings-guide">
    <h3>从今天开始</h3>
    <ol className="help-steps">
      <li>写下一件想做的事，按回车添加。输入法确认文字时不会提交。</li>
      <li>做完后勾选，事项会收进「已完成」。展开后取消勾选即可恢复。</li>
      <li>更多操作点「···」或右键；误删时，3 秒内点击底部「撤销」。</li>
    </ol>

    <details className="settings-details"><summary>完成、详情与改期</summary>
      <p>点击标题编辑标题和备注，保存后生效；保存失败会保留输入。备注是纯文本，最多 10000 字。</p>
      <p>完成后会短暂停留再收纳。今天和未来的「已完成」默认折叠，过去的记录默认展开、仅供回看。</p>
      <p>在「···」或右键菜单中，可把未完成的计划安排到今天、明天或指定日期，也可移回待办。直接改期会保留标题、备注和时间；移回待办会清除当天时间。零碎事项不能跨日移动。</p>
      <p>「设置时间」可单独填写开始或结束，按 5 分钟间隔填写；点「清除」后保存即可移除时间。时间是提示，不会触发通知。</p>
    </details>

    <details className="settings-details"><summary>搜索、排序与快速录入</summary>
      <p>点击顶部搜索图标，或按 ⌘ / Ctrl + K，查找标题和备注。范围为待办、今天和未来的未完成事项；已完成及历史记录请切换日期查看。↑ ↓ 选择，回车定位。</p>
      <p>鼠标移到计划或零碎事项上，拖动左侧把手排序；聚焦把手后可按 Option / Alt + ↑ ↓。手动顺序会保留，点列表标题旁的「按时间」可恢复时间排序。折叠的完成项不会丢失顺序。</p>
      <p>桌面版默认按 ⌃ ⌥ Space 打开快速录入，选择「待办」或「今天」后回车添加。Esc 收起并保留草稿，也可通过「文件」菜单打开。快捷键可在设置中更改；关闭主窗口后应用仍在运行，⌘ Q 才会退出。</p>
    </details>

    <details className="settings-details"><summary>待办、零碎事项与定期事项</summary>
      <dl>
        <dt>计划 · 当天要推进的事</dt><dd>未完成的计划第二天回到「待办」，由你决定何时再做。</dd>
        <dt>待办 · 以后再做的事</dt><dd>参考日期只是提示，不会自动安排。菜单中「标记已完成」会记入今天的完成记录。</dd>
        <dt>零碎事项 · 只属于当天的小事</dt><dd>不会带到明天，未完成事项留在当天历史中，显示为已作废。</dd>
        <dt>定期事项 · 每天或每周重复的事</dt><dd>勾选一次只完成当天事项。暂停后不生成新事项，可恢复；停止后不能恢复。</dd>
      </dl>
      <p className="settings-caption">日期按北京时间（Asia/Shanghai）计算。参考日期与计划日期不同，过去的日期只读。</p>
    </details>

    <details className="settings-details"><summary>目标与阶段</summary>
      <p>「目标」适合记录需要一段时间完成的方向，例如通过认证或整理作品集。写下目标后，再从行动中选一件「下一步」。</p>
      <p>阶段是可选的扁平标签，可排序、设为当前、完成、跳过或重新打开。它不会自动完成、删除或改期其中的行动。</p>
      <p>暂停或结束目标不会改动已有待办和今天的安排。结束后仍可重新打开；大致时间只作参考。</p>
    </details>

    <details className="settings-details"><summary>使用计划助手</summary>
      <p>先在「计划助手」分区连接工具并检测环境，再打开主界面右上角的「计划助手」输入指令。</p>
      <AssistantUsage />
      <dl>
        <dt>暂停，再继续</dt><dd>点击「暂停」挂起本机执行。不改指令，点「继续执行」可从暂停处继续；远端请求可能仍在执行。</dd>
        <dt>调整指令</dt><dd>暂停后编辑输入框，点「按新指令继续」。保留已有改动，读取当前计划并开始新执行。</dd>
        <dt>停止本次</dt><dd>结束执行并保留已有改动。收起面板不会停止执行；退出应用会结束执行，下次打开不能接续原进程。</dd>
      </dl>
    </details>

    <details className="settings-details"><summary>备份与恢复</summary>
      <p>「数据与备份」中可立即备份，或展开列表下载。换电脑时选择备份文件并确认恢复。备份包含事项、备注、历史与排序；助手配置和主题需另行设置。</p>
      <p className="settings-caption">恢复前会自动备份当前数据。若助手正在执行或暂停，请先停止本次执行。</p>
    </details>

    <details className="settings-details"><summary>快捷键速查</summary>
      <CommonShortcuts />
      <dl className="settings-keyboard-list">
        <div><dt>添加事项</dt><dd><kbd>Enter</kbd></dd></div>
        <div><dt>发送助手指令</dt><dd><kbd>{sendLabel}</kbd></dd></div>
        <div><dt>助手指令换行</dt><dd><kbd>{newlineLabel}</kbd></dd></div>
      </dl>
      <p className="settings-caption">发送方式和桌面全局录入快捷键可在「快捷键」分区更改。助手面板打开时，Esc 先关闭内部菜单，再收起面板。</p>
    </details>
  </div>;
}

export function AboutAuthor() {
  return <div className="help-content settings-about">
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
  </div>;
}
