# macOS 桌面版本

2026-09-26 用户明确要求「把 local todo 转化成 macOS 桌面端软件」。这次请求授权新增桌面入口，覆盖 v1 技术设计中原生套壳的旧非目标；不扩大计划功能范围。

## 本次交付

- 显示名延续 Local Planner；可在 Finder 双击 `.app`，拥有独立窗口、Dock 图标、原生菜单。
- 复用当前工作树的界面和领域逻辑，保留今天、库存、定期事项、每日规划及现有助手能力。
- 打包前端、Python 和依赖，运行应用不需要另装 Python、Node.js 或保留源码。可选的外部助手仍使用用户自己安装和配置的 CLI。
- 数据继续存放在 `~/Library/Application Support/local-planner/`，数据库不迁到应用包内；已有数据及命令行可继续使用。`LOCAL_PLANNER_DATA_DIR` 可用于隔离测试。
- 桌面窗口使用自己的本地服务，只绑定 `127.0.0.1`，优先端口 18787；被占用时申请空闲端口。网页版的 8787 服务保持独立，数据库依靠既有锁协调。
- 关闭最后一个窗口或按 Cmd+Q 退出应用时，结束本次桌面服务及它启动的助手进程；应用进程退出时由父子进程管道触发同样的清理。重新打开会按领域规则补做日界结转。
- 支持 Cmd+C/V/X/A、Cmd+R 刷新、Cmd+1/2/3/4 切换今天/待办/定期事项/目标，Cmd+N 新增事项，菜单中可打开数据目录和日志。
- 桌面主题选择保存到该应用的本机偏好，服务端口变化或重启后仍恢复；旧桌面版本在当前端口留有主题时会迁移该值。普通网页仍使用自身的 localStorage。其他浏览器偏好由桌面 WebKit 单独保存，待办数据共享；不自动迁移外部浏览器的 localStorage。

## 构建与维护

需要 macOS、Xcode Command Line Tools、Python 3.12+、Node.js。仓库根目录执行：

```sh
.venv/bin/python -m pip install -e '.[dev]' -r desktop/macos/requirements-build.txt
.venv/bin/python scripts/build_macos.py --install
```

产物为 `dist/macos/Local Planner.app` 和按当前 CPU 架构生成的 ZIP。`--install` 安装到 `~/Applications`，已有同名应用时拒绝覆盖。修改代码后重新构建、退出并移走旧应用，再安装新应用。数据目录独立于应用包，更新应用无需移动数据库。

构建架构与当前 Mac 相同，最低系统版本根据包内 Python 和动态库的实际要求写入 Info.plist。本次使用本机 Homebrew Python，在 Apple Silicon / macOS 26 上构建验证，产物要求 macOS 26.0+；未验证 Intel 或更旧的系统。

日志在数据目录 `desktop.log`。退出应用后，桌面服务应不再监听。构建使用本机 ad-hoc 签名，适合本机使用；没有 Developer ID 签名、公证或 App Store 发布。

打包后的 CLI 入口：

```sh
"$HOME/Applications/Local Planner.app/Contents/Resources/backend/local-planner-backend" context
"$HOME/Applications/Local Planner.app/Contents/Resources/backend/local-planner-backend" backup
```

## 尚未要求的分发事项

面向其他用户的签名公证、Intel/Universal 构建、自动更新和商店分发尚未决策，不作为本次本机桌面化的需求。

下一轮日常交互与助手控制见 [日常体验打磨](daily-experience.md)。

应用内设置、备份导入与原生保存窗口见 [第一批用户的使用体验](first-users.md)。

## 独立设置窗口

2026-09-27 用户要求设置改为弹出的独立窗口。

- 桌面导航的「设置」、Cmd+,、助手的「连接助手」打开同一个原生设置窗口。重复打开只将它带到前台，不重新载入主页面，保留事项草稿与助手执行状态。
- 2026-09-28 按用户要求改为左侧固定分区导航、右侧内容布局，全部六个分区第一眼可见，仅长内容在右侧滚动。新窗口默认 840 × 620，最小 640 × 480，可独立移动与调整大小，不重复显示主导航和助手面板。右上角关闭按钮、窗口红色按钮或 Cmd+W 只关闭设置窗口。
- 「使用说明」「关于作者」及应用的「关于」菜单使用此窗口并切换到对应分区；助手「连接助手」直接选择助手分区。再次打开设置时保留所选分区和未提交的配置草稿。
- 主题更改立即反映到主窗口，助手配置保存后刷新助手选择与环境状态，恢复备份后刷新主窗口事项并清除失效的撤销提示。
- 文件选择、备份保存及提示对话框附着在发起操作的窗口；重新载入与缩放作用于当前窗口。所有窗口共用一个本地服务。
- 浏览器访问继续使用现有设置页面，桌面窗口控制仅由本机原生桥接提供。
