import AppKit
import WebKit
import Carbon

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate, WKScriptMessageHandler, NSTextFieldDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var settingsWindow: NSWindow?
    private var settingsWebView: WKWebView?
    private var pendingSettingsFragment: String?
    private var pendingAssistantOpen = false
    private var entryPanel: NSPanel?
    private var entryTitle: NSTextField?
    private var entryDestination: NSSegmentedControl?
    private var entrySave: NSButton?
    private var entryStatus: NSTextField?
    private var entryBusy = false
    private var hotKey: EventHotKeyRef?
    private var hotKeyHandler: EventHandlerRef?
    private var shortcutStatus = ""
    private var quickEntryMenuItem: NSMenuItem?
    private var quickShortcut: String { UserDefaults.standard.string(forKey: "quickEntryShortcut") ?? "ctrl-option-space" }
    private var backend: Process?
    private let lifetime = Pipe()
    private var output: Pipe?
    private var logFile: FileHandle?
    private var startupTimer: Timer?
    private var completionMonitor: AgentCompletionMonitor?
    private var baseURL: URL?
    private var quitting = false
    private var failed = false
    private let themePreferenceKey = "plannerTheme"
    private let themeIds: Set<String> = ["warm-paper", "midnight", "nordic", "forest", "retro"]
    private var planningFocusKey: String { "planningFocus:" + dataDirectory.standardizedFileURL.path }
    private var planningFocusJSON: String {
        let ids = UserDefaults.standard.stringArray(forKey: planningFocusKey) ?? []
        guard let data = try? JSONSerialization.data(withJSONObject: ids), let json = String(data: data, encoding: .utf8) else { return "[]" }
        return json
    }

    private var dataDirectory: URL {
        if let path = ProcessInfo.processInfo.environment["LOCAL_PLANNER_DATA_DIR"] {
            return URL(fileURLWithPath: (path as NSString).expandingTildeInPath)
        }
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/local-planner", isDirectory: true)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Finder normally enforces this; also cover directly running the executable.
        if let id = Bundle.main.bundleIdentifier,
           let existing = NSRunningApplication.runningApplications(withBundleIdentifier: id)
            .first(where: { $0.processIdentifier != ProcessInfo.processInfo.processIdentifier }) {
            existing.activate(options: [.activateAllWindows])
            NSApp.terminate(nil)
            return
        }
        buildMenu()
        buildWindow()
        startBackend()
        installQuickEntryShortcut()
    }

    private func buildWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1320, height: 860),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Local Planner"
        window.minSize = NSSize(width: 900, height: 620)
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.center()
        window.setFrameAutosaveName("LocalPlannerMainWindow")
        let loading = NSView()
        let label = NSTextField(labelWithString: "正在打开 Local Planner…")
        label.font = .systemFont(ofSize: 17, weight: .medium)
        let spinner = NSProgressIndicator()
        spinner.style = .spinning
        spinner.startAnimation(nil)
        for view in [label, spinner] {
            view.translatesAutoresizingMaskIntoConstraints = false
            loading.addSubview(view)
        }
        NSLayoutConstraint.activate([
            label.centerXAnchor.constraint(equalTo: loading.centerXAnchor),
            label.centerYAnchor.constraint(equalTo: loading.centerYAnchor, constant: 20),
            spinner.centerXAnchor.constraint(equalTo: loading.centerXAnchor),
            spinner.bottomAnchor.constraint(equalTo: label.topAnchor, constant: -20)
        ])
        window.contentView = loading
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func buildMenu() {
        let bar = NSMenu()
        func menu(_ title: String) -> NSMenu {
            let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
            let submenu = NSMenu(title: title)
            item.submenu = submenu
            bar.addItem(item)
            return submenu
        }
        func add(_ menu: NSMenu, _ title: String, _ action: Selector, _ key: String = "", target: AnyObject? = nil) {
            let item = NSMenuItem(title: title, action: action, keyEquivalent: key)
            item.target = target
            menu.addItem(item)
        }
        let app = menu("Local Planner")
        add(app, "关于 Local Planner", #selector(goAbout), target: self)
        add(app, "设置…", #selector(goSettings), ",", target: self)
        app.addItem(.separator())
        add(app, "隐藏 Local Planner", #selector(NSApplication.hide(_:)), "h")
        add(app, "显示全部", #selector(NSApplication.unhideAllApplications(_:)))
        app.addItem(.separator())
        add(app, "退出 Local Planner", #selector(NSApplication.terminate(_:)), "q")
        let file = menu("文件")
        add(file, "新增事项", #selector(quickAdd), "n", target: self)
        let entryItem = NSMenuItem(title: "快速录入…", action: #selector(showQuickEntry), keyEquivalent: "")
        entryItem.target = self
        quickEntryMenuItem = entryItem
        file.addItem(entryItem)
        file.addItem(.separator())
        add(file, "打开数据文件夹", #selector(showData), target: self)
        add(file, "打开运行日志", #selector(showLog), target: self)
        file.addItem(.separator())
        add(file, "关闭窗口", #selector(NSWindow.performClose(_:)), "w")
        let edit = menu("编辑")
        for (title, action, key) in [("撤销", "undo:", "z"), ("重做", "redo:", "Z"),
                                    ("剪切", "cut:", "x"), ("复制", "copy:", "c"),
                                    ("粘贴", "paste:", "v"), ("全选", "selectAll:", "a")] {
            add(edit, title, Selector(action), key)
        }
        let view = menu("显示")
        add(view, "搜索事项…", #selector(searchItems), "k", target: self)
        let assistantItem = NSMenuItem(title: "打开计划助手", action: #selector(openAssistant), keyEquivalent: "l")
        assistantItem.keyEquivalentModifierMask = [.command, .shift]
        assistantItem.target = self
        view.addItem(assistantItem)
        add(view, "今天", #selector(goToday), "1", target: self)
        add(view, "待办", #selector(goInventory), "2", target: self)
        add(view, "定期事项", #selector(goRecurrences), "3", target: self)
        add(view, "规划", #selector(goGoals), "4", target: self)
        view.addItem(.separator())
        add(view, "重新载入", #selector(reload), "r", target: self)
        add(view, "放大", #selector(zoomIn), "=", target: self)
        add(view, "缩小", #selector(zoomOut), "-", target: self)
        add(view, "实际大小", #selector(resetZoom), "0", target: self)
        let win = menu("窗口")
        add(win, "最小化", #selector(NSWindow.performMiniaturize(_:)), "m")
        add(win, "缩放", #selector(NSWindow.performZoom(_:)))
        NSApp.windowsMenu = win
        let help = menu("帮助")
        add(help, "Local Planner 使用说明", #selector(goHelp), target: self)
        add(help, "关于作者", #selector(goAbout), target: self)
        NSApp.helpMenu = help
        NSApp.mainMenu = bar
    }

    private func startBackend() {
        do {
            try FileManager.default.createDirectory(at: dataDirectory, withIntermediateDirectories: true)
            let logURL = dataDirectory.appendingPathComponent("desktop.log")
            if !FileManager.default.fileExists(atPath: logURL.path) {
                FileManager.default.createFile(atPath: logURL.path, contents: nil)
            }
            logFile = try FileHandle(forWritingTo: logURL)
            try logFile?.seekToEnd()
            guard let resources = Bundle.main.resourceURL else { throw CocoaError(.fileNoSuchFile) }
            let process = Process()
            process.executableURL = resources.appendingPathComponent("backend/local-planner-backend")
            process.arguments = ["desktop-serve"]
            process.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser
            var env = ProcessInfo.processInfo.environment
            env.removeValue(forKey: "LOCAL_PLANNER_DEV")
            env["LOCAL_PLANNER_DATA_DIR"] = dataDirectory.path
            // Finder has a minimal PATH. Preserve user overrides and common CLI installs.
            let home = FileManager.default.homeDirectoryForCurrentUser.path
            env["PATH"] = ([env["PATH"] ?? "", "\(home)/.local/bin", "\(home)/.opencode/bin",
                            "\(home)/.bun/bin", "\(home)/bin", "/opt/homebrew/bin",
                            "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]).joined(separator: ":")
            process.environment = env
            process.standardInput = lifetime
            let pipe = Pipe()
            output = pipe
            process.standardOutput = pipe
            process.standardError = logFile
            process.terminationHandler = { [weak self] task in
                DispatchQueue.main.async {
                    guard let self else { return }
                    if self.quitting { NSApp.reply(toApplicationShouldTerminate: true) }
                    else { self.showFailure("本地服务已退出（\(task.terminationStatus)）。可打开日志查看原因。") }
                }
            }
            backend = process
            try process.run()
            // Only the child owns the pipe read end; closing the app causes EOF.
            try? lifetime.fileHandleForReading.close()
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                var buffer = Data()
                while true {
                    let data = pipe.fileHandleForReading.availableData
                    if data.isEmpty { break }
                    buffer.append(data)
                    while let newline = buffer.firstIndex(of: 10) {
                        let line = Data(buffer[..<newline])
                        buffer.removeSubrange(...newline)
                        if let event = try? JSONSerialization.jsonObject(with: line) as? [String: String],
                           event["event"] == "ready", let rawURL = event["url"], let url = URL(string: rawURL) {
                            DispatchQueue.main.async { self?.loadApp(url) }
                        }
                    }
                }
            }
            startupTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: false) { [weak self] _ in
                self?.showFailure("启动超时。可打开运行日志查看原因，然后重新打开应用。")
            }
        } catch {
            showFailure("无法启动本地服务：\(error.localizedDescription)")
        }
    }

    private func loadApp(_ url: URL) {
        guard !quitting, !failed, baseURL == nil, url.scheme == "http", url.host == "127.0.0.1",
              let port = url.port, (1...65535).contains(port) else { return }
        startupTimer?.invalidate()
        baseURL = url
        completionMonitor = AgentCompletionMonitor(baseURL: url, mainWindowReadable: { [weak self] in
            self?.mainWindowReadable == true
        }, updateBadge: { label in
            NSApp.dockTile.badgeLabel = label
        })
        completionMonitor?.start()
        webView = makeWebView(frame: window.contentView!.bounds, kind: "main")
        webView.allowsBackForwardNavigationGestures = true
        window.contentView = webView
        webView.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
        window.makeFirstResponder(webView)
    }

    private func makeWebView(frame: NSRect, kind: String) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.userContentController.add(self, name: "plannerDesktop")
        let savedTheme = UserDefaults.standard.string(forKey: themePreferenceKey)
        let themeValue = savedTheme.flatMap { themeIds.contains($0) ? "'\($0)'" : nil } ?? "null"
        let processValue = UserDefaults.standard.bool(forKey: "assistantShowProcess") ? "true" : "false"
        configuration.userContentController.addUserScript(WKUserScript(
            source: "window.__PLANNER_DESKTOP_WINDOW__ = '\(kind)'; window.__PLANNER_DESKTOP_THEME__ = \(themeValue); window.__PLANNER_DESKTOP_ASSISTANT_PROCESS__ = \(processValue); window.__PLANNER_DESKTOP_PLANNING_FOCUS__ = \(planningFocusJSON);",
            injectionTime: .atDocumentStart, forMainFrameOnly: true))
        let view = WKWebView(frame: frame, configuration: configuration)
        view.navigationDelegate = self
        view.uiDelegate = self
        view.autoresizingMask = [.width, .height]
        return view
    }

    private func showSettings(fragment: String? = nil) {
        guard let baseURL else { return }
        if settingsWindow == nil {
            let settings = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 840, height: 620),
                                    styleMask: [.titled, .closable, .miniaturizable, .resizable],
                                    backing: .buffered, defer: false)
            settings.title = "设置 · Local Planner"
            settings.minSize = NSSize(width: 640, height: 480)
            settings.isReleasedWhenClosed = false
            settings.center()
            settings.setFrameAutosaveName("LocalPlannerSettingsWindow")
            let view = makeWebView(frame: settings.contentView!.bounds, kind: "settings")
            settings.contentView = view
            settingsWindow = settings
            settingsWebView = view
            pendingSettingsFragment = fragment
            view.load(URLRequest(url: baseURL.appendingPathComponent("settings"), cachePolicy: .reloadIgnoringLocalCacheData))
        } else {
            settingsWebView?.evaluateJavaScript("window.dispatchEvent(new Event('planner:settings-opened'))")
            if let fragment {
                if settingsWebView?.isLoading == true { pendingSettingsFragment = fragment }
                else { revealSettingsSection(fragment) }
            }
        }
        settingsWindow?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func revealSettingsSection(_ fragment: String) {
        guard ["appearance", "assistant", "shortcuts", "data", "help", "about"].contains(fragment) else { return }
        // Notify even when the requested section is already in the URL.
        settingsWebView?.evaluateJavaScript("window.location.hash = '\(fragment)'; window.dispatchEvent(new HashChangeEvent('hashchange'))")
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if webView === self.webView && pendingAssistantOpen {
            pendingAssistantOpen = false
            openAssistant()
        }
        if webView === settingsWebView, let fragment = pendingSettingsFragment {
            pendingSettingsFragment = nil
            revealSettingsSection(fragment)
        }
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "plannerDesktop", message.frameInfo.isMainFrame,
              let source = message.webView, source === webView || source === settingsWebView,
              let url = message.frameInfo.request.url, isLocal(url),
              let body = message.body as? [String: Any], let action = body["action"] as? String else { return }
        switch action {
        case "openSettings":
            showSettings(fragment: body["fragment"] as? String)
        case "closeSettings":
            if source === settingsWebView { settingsWindow?.performClose(nil) }
        case "getQuickShortcut":
            sendShortcutState(to: source)
        case "setQuickShortcut":
            if let value = body["value"] as? String { configureShortcut(value); sendShortcutState(to: source) }
        case "getAssistantPreferences":
            let value = UserDefaults.standard.bool(forKey: "assistantShowProcess") ? "true" : "false"
            source.evaluateJavaScript("window.__PLANNER_DESKTOP_ASSISTANT_PROCESS__ = \(value); window.dispatchEvent(new CustomEvent('planner:assistant-preferences-changed', {detail: '\(value)'}))")
        case "getPlanningFocus":
            source.evaluateJavaScript("window.__PLANNER_DESKTOP_PLANNING_FOCUS__ = \(planningFocusJSON); window.dispatchEvent(new CustomEvent('planner:planning-focus-changed', {detail: \(planningFocusJSON)}))")
        case "setPlanningFocus":
            guard source === webView, let ids = body["goalIds"] as? [String], ids.count <= 100,
                  ids.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && $0.count <= 100 }),
                  Set(ids).count == ids.count else { return }
            UserDefaults.standard.set(ids, forKey: planningFocusKey)
            settingsWebView?.evaluateJavaScript("window.__PLANNER_DESKTOP_PLANNING_FOCUS__ = \(planningFocusJSON); window.dispatchEvent(new CustomEvent('planner:planning-focus-changed', {detail: \(planningFocusJSON)}))")
        case "setTheme":
            if let value = body["value"] as? String, themeIds.contains(value) {
                UserDefaults.standard.set(value, forKey: themePreferenceKey)
            }
        case "settingsChanged":
            guard let event = body["event"] as? String,
                  ["planner:restored", "planner:launchers-changed", "planner:theme-changed", "planner:shortcuts-changed", "planner:assistant-preferences-changed"].contains(event),
                  let data = try? JSONSerialization.data(withJSONObject: body),
                  let json = String(data: data, encoding: .utf8) else { return }
            if event == "planner:theme-changed" {
                guard let value = body["detail"] as? String, themeIds.contains(value) else { return }
                UserDefaults.standard.set(value, forKey: themePreferenceKey)
            }
            if event == "planner:assistant-preferences-changed" {
                guard let value = body["detail"] as? String, ["true", "false"].contains(value) else { return }
                UserDefaults.standard.set(value == "true", forKey: "assistantShowProcess")
            }
            if event == "planner:restored" { completionMonitor?.reset() }
            let other = source === settingsWebView ? webView : settingsWebView
            other?.evaluateJavaScript("{ const message = \(json); window.dispatchEvent(new CustomEvent(message.event, {detail: message.detail})); }")
        default: break
        }
    }

    private func isLocal(_ url: URL) -> Bool {
        url.scheme == baseURL?.scheme && url.host == baseURL?.host && url.port == baseURL?.port
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if isLocal(url) {
            if webView === self.webView && url.path == "/settings" {
                showSettings(fragment: url.fragment)
                decisionHandler(.cancel)
            } else { decisionHandler(navigationAction.shouldPerformDownload ? .download : .allow) }
            return
        }
        if navigationAction.navigationType == .linkActivated && ["https", "http", "mailto"].contains(url.scheme ?? "") {
            NSWorkspace.shared.open(url)
        }
        decisionHandler(.cancel)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, isLocal(url) { webView.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData)) }
        return nil
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        guard let url = navigationResponse.response.url, isLocal(url) else { decisionHandler(.cancel); return }
        decisionHandler(navigationResponse.canShowMIMEType ? .allow : .download)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        panel.title = "保存备份"
        panel.canCreateDirectories = true
        panel.beginSheetModal(for: download.webView?.window ?? window) { result in
            completionHandler(result == .OK ? panel.url : nil)
        }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        if (error as NSError).code == NSURLErrorCancelled { return }
        let alert = NSAlert()
        alert.messageText = "备份未保存"
        alert.informativeText = "请检查目标文件夹和磁盘空间后重试。"
        alert.beginSheetModal(for: download.webView?.window ?? window)
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.title = "选择 Local Planner 备份"
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.beginSheetModal(for: webView.window ?? window) { result in
            completionHandler(result == .OK ? panel.urls : nil)
        }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if NavigationFailure.isExpectedInterruption(error) {
            let failure = error as NSError
            FileHandle.standardError.write(Data("Ignored navigation interruption: domain=\(failure.domain) code=\(failure.code)\n".utf8))
            return
        }
        if webView === settingsWebView, let settingsWindow {
            let alert = NSAlert()
            alert.messageText = "设置暂时无法打开"
            alert.informativeText = "请按 ⌘R 重新载入。\(error.localizedDescription)"
            alert.beginSheetModal(for: settingsWindow)
        } else { showFailure("页面加载失败：\(error.localizedDescription)") }
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { webView.reload() }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "确定")
        alert.addButton(withTitle: "取消")
        alert.beginSheetModal(for: webView.window ?? window) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.beginSheetModal(for: webView.window ?? window) { _ in completionHandler() }
    }

    private func showFailure(_ message: String) {
        guard !quitting, !failed else { return }
        failed = true
        startupTimer?.invalidate()
        let alert = NSAlert()
        alert.messageText = "Local Planner 无法打开"
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.addButton(withTitle: "退出")
        alert.addButton(withTitle: "查看日志并退出")
        if alert.runModal() == .alertSecondButtonReturn { showLog() }
        NSApp.terminate(nil)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    private var mainWindowReadable: Bool {
        NSApp.isActive && window?.isKeyWindow == true && window?.isVisible == true &&
        window?.isMiniaturized == false && window?.attachedSheet == nil && NSApp.modalWindow == nil
    }

    func applicationDidBecomeActive(_ notification: Notification) { completionMonitor?.acknowledge() }

    func windowDidBecomeKey(_ notification: Notification) {
        if notification.object as? NSWindow === window { completionMonitor?.acknowledge() }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window?.makeKeyAndOrderFront(nil)
        return true
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if quitting { return .terminateLater }
        quitting = true
        if let hotKey { UnregisterEventHotKey(hotKey) }
        if let hotKeyHandler { RemoveEventHandler(hotKeyHandler) }
        startupTimer?.invalidate()
        completionMonitor?.stop()
        NSApp.dockTile.badgeLabel = nil
        try? lifetime.fileHandleForWriting.close()
        guard let process = backend, process.isRunning else { return .terminateNow }
        // EOF triggers backend cleanup, including any agent process groups.
        DispatchQueue.main.asyncAfter(deadline: .now() + 10) {
            if process.isRunning { kill(process.processIdentifier, SIGKILL) }
            NSApp.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }

    private func installQuickEntryShortcut() {
        var event = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let status = InstallEventHandler(GetApplicationEventTarget(), { _, event, context in
            guard let context, let event else { return OSStatus(eventNotHandledErr) }
            var id = EventHotKeyID()
            let status = GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil,
                                           MemoryLayout<EventHotKeyID>.size, nil, &id)
            guard status == noErr, id.signature == 0x4C504C4E, id.id == 1 else { return OSStatus(eventNotHandledErr) }
            let delegate = Unmanaged<AppDelegate>.fromOpaque(context).takeUnretainedValue()
            delegate.showQuickEntry()
            return noErr
        }, 1, &event, Unmanaged.passUnretained(self).toOpaque(), &hotKeyHandler)
        guard status == noErr else { shortcutStatus = "快捷键暂时不可用，可通过「文件 → 快速录入」打开。"; return }
        configureShortcut(quickShortcut)
    }

    private func configureShortcut(_ value: String) {
        guard ["ctrl-option-space", "ctrl-shift-space", "off"].contains(value) else { return }
        if value == "off" {
            if let hotKey { UnregisterEventHotKey(hotKey) }
            hotKey = nil
        } else {
            if value == quickShortcut && hotKey != nil { shortcutStatus = ""; return }
            guard hotKeyHandler != nil else { shortcutStatus = "快捷键暂时不可用，可通过「文件 → 快速录入」打开。"; return }
            var next: EventHotKeyRef?
            let modifiers = UInt32(controlKey | (value == "ctrl-option-space" ? optionKey : shiftKey))
            let result = RegisterEventHotKey(UInt32(kVK_Space), modifiers,
                EventHotKeyID(signature: 0x4C504C4E, id: 1), GetApplicationEventTarget(), OptionBits(kEventHotKeyExclusive), &next)
            guard result == noErr else {
                shortcutStatus = hotKey == nil ? "快捷键已被占用，请选择另一组；也可从「文件」菜单录入。" : "这组快捷键已被占用，已保留原设置。"
                return
            }
            if let hotKey { UnregisterEventHotKey(hotKey) }
            hotKey = next
        }
        quickEntryMenuItem?.keyEquivalent = value == "off" ? "" : " "
        quickEntryMenuItem?.keyEquivalentModifierMask = value == "ctrl-shift-space" ? [.control, .shift] : [.control, .option]
        UserDefaults.standard.set(value, forKey: "quickEntryShortcut")
        shortcutStatus = ""
    }

    private func sendShortcutState(to view: WKWebView) {
        let state: [String: Any] = ["value": quickShortcut, "message": shortcutStatus, "active": hotKey != nil]
        guard let data = try? JSONSerialization.data(withJSONObject: state), let json = String(data: data, encoding: .utf8) else { return }
        view.evaluateJavaScript("window.dispatchEvent(new CustomEvent('planner:quick-shortcut-state', {detail: \(json)}))")
    }

    @objc private func showQuickEntry() {
        guard baseURL != nil, !quitting, !failed else { return }
        if entryPanel == nil {
            let panel = QuickEntryPanel(contentRect: NSRect(x: 0, y: 0, width: 540, height: 182),
                styleMask: [.titled, .closable, .nonactivatingPanel], backing: .buffered, defer: false)
            panel.title = "快速录入 · Local Planner"
            panel.isReleasedWhenClosed = false
            panel.level = .floating
            panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
            panel.hidesOnDeactivate = false
            panel.onCancel = { [weak self] in self?.closeQuickEntry() }
            let content = NSView()
            panel.contentView = content
            let title = NSTextField(string: "")
            title.placeholderString = "先记下一件事…"
            title.font = .systemFont(ofSize: 19)
            title.bezelStyle = .roundedBezel
            title.delegate = self
            let destination = NSSegmentedControl(labels: ["待办", "今天"], trackingMode: .selectOne, target: nil, action: nil)
            destination.selectedSegment = 0
            destination.setAccessibilityLabel("添加到")
            let save = NSButton(title: "添加", target: self, action: #selector(submitQuickEntry))
            save.bezelStyle = .rounded
            let status = NSTextField(wrappingLabelWithString: "")
            status.font = .systemFont(ofSize: 12)
            status.textColor = .secondaryLabelColor
            for view in [title, destination, save, status] {
                view.translatesAutoresizingMaskIntoConstraints = false
                content.addSubview(view)
            }
            NSLayoutConstraint.activate([
                title.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 24),
                title.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -24),
                title.topAnchor.constraint(equalTo: content.topAnchor, constant: 24),
                title.heightAnchor.constraint(equalToConstant: 44),
                destination.leadingAnchor.constraint(equalTo: title.leadingAnchor),
                destination.topAnchor.constraint(equalTo: title.bottomAnchor, constant: 16),
                save.trailingAnchor.constraint(equalTo: title.trailingAnchor),
                save.centerYAnchor.constraint(equalTo: destination.centerYAnchor),
                save.widthAnchor.constraint(equalToConstant: 76),
                status.leadingAnchor.constraint(equalTo: title.leadingAnchor),
                status.trailingAnchor.constraint(equalTo: title.trailingAnchor),
                status.topAnchor.constraint(equalTo: destination.bottomAnchor, constant: 10),
                status.bottomAnchor.constraint(lessThanOrEqualTo: content.bottomAnchor, constant: -10)
            ])
            entryPanel = panel; entryTitle = title; entryDestination = destination; entrySave = save; entryStatus = status
        }
        if entryPanel?.isVisible != true { entryPanel?.center() }
        entryPanel?.makeKeyAndOrderFront(nil)
        if !entryBusy { entryPanel?.makeFirstResponder(entryTitle) }
    }

    private func closeQuickEntry() {
        guard !entryBusy else { return }
        entryPanel?.orderOut(nil)
    }

    func control(_ control: NSControl, textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
        guard control === entryTitle, !textView.hasMarkedText() else { return false }
        if commandSelector == #selector(NSResponder.cancelOperation(_:)) { closeQuickEntry(); return true }
        if commandSelector == #selector(NSResponder.insertNewline(_:)) { submitQuickEntry(); return true }
        return false
    }

    private func setEntryBusy(_ busy: Bool) {
        entryBusy = busy
        entryTitle?.isEnabled = !busy
        entryDestination?.isEnabled = !busy
        entrySave?.isEnabled = !busy
        entrySave?.title = busy ? "添加中…" : "添加"
        entryPanel?.standardWindowButton(.closeButton)?.isEnabled = !busy
    }

    @objc private func submitQuickEntry() {
        guard !entryBusy, let baseURL, let field = entryTitle else { return }
        if let editor = field.currentEditor() as? NSTextView, editor.hasMarkedText() { return }
        let title = field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else { field.becomeFirstResponder(); return }
        guard title.count <= 200 else { entryStatus?.stringValue = "标题最长 200 字。"; return }
        var request = URLRequest(url: baseURL.appendingPathComponent("api/quick-entry"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["title": title, "destination": entryDestination?.selectedSegment == 1 ? "today" : "inventory"])
        entryStatus?.stringValue = ""
        setEntryBusy(true)
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            let json = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
            DispatchQueue.main.async {
                guard let self else { return }
                self.setEntryBusy(false)
                if (200..<300).contains(status), error == nil {
                    self.entryTitle?.stringValue = ""
                    self.entryStatus?.stringValue = ""
                    self.entryPanel?.orderOut(nil)
                    self.webView?.evaluateJavaScript("window.dispatchEvent(new Event('planner:items-changed'))")
                } else {
                    self.entryStatus?.stringValue = json?["message"] as? String ?? "未能确认保存，请先检查列表再重试。输入已保留。"
                    self.entryPanel?.makeFirstResponder(self.entryTitle)
                }
            }
        }.resume()
    }

    private func navigate(_ path: String, fragment: String? = nil) {
        guard let baseURL,
              var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false) else { return }
        components.fragment = fragment
        guard let url = components.url else { return }
        window?.makeKeyAndOrderFront(nil)
        webView?.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
    }
    @objc private func quickAdd() {
        window?.makeKeyAndOrderFront(nil)
        webView?.evaluateJavaScript("document.querySelector('.add-form input, .inventory-add-form input') !== null") { [weak self] result, _ in
            if result as? Bool == true {
                self?.webView?.evaluateJavaScript("window.dispatchEvent(new Event('planner:quick-add'))")
            } else if let url = self?.baseURL {
                self?.webView?.load(URLRequest(url: url.appending(queryItems: [URLQueryItem(name: "add", value: "1")])))
            }
        }
    }
    @objc private func searchItems() {
        window?.makeKeyAndOrderFront(nil)
        webView?.evaluateJavaScript("window.dispatchEvent(new Event('planner:search'))")
    }

    @objc private func openAssistant() {
        guard !quitting, !failed, baseURL != nil, NSApp.modalWindow == nil,
              !NSApp.windows.contains(where: { $0.attachedSheet != nil }) else { return }
        if let input = NSApp.keyWindow?.firstResponder as? NSTextInputClient, input.hasMarkedText() { return }
        // Query before raising the main window so web dialogs do not lose focus.
        activeWebView?.evaluateJavaScript("Boolean(document.querySelector('dialog[open]'))") { [weak self] value, error in
            guard let self, error == nil, (value as? Bool) != true else { return }
            self.window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            if self.webView.isLoading { self.pendingAssistantOpen = true }
            else { self.webView.evaluateJavaScript("window.dispatchEvent(new Event('planner:open-assistant'))") }
        }
    }
    @objc private func goToday() { navigate("") }
    @objc private func goInventory() { navigate("inventory") }
    @objc private func goRecurrences() { navigate("recurrences") }
    @objc private func goGoals() { navigate("goals") }
    @objc private func goSettings() { showSettings() }
    @objc private func goHelp() { showSettings(fragment: "help") }
    @objc private func goAbout() { showSettings(fragment: "about") }
    private var activeWebView: WKWebView? { NSApp.keyWindow === settingsWindow ? settingsWebView : webView }
    @objc private func reload() { activeWebView?.reloadFromOrigin() }
    @objc private func zoomIn() { if let view = activeWebView { view.pageZoom = min(2, view.pageZoom + 0.1) } }
    @objc private func zoomOut() { if let view = activeWebView { view.pageZoom = max(0.6, view.pageZoom - 0.1) } }
    @objc private func resetZoom() { activeWebView?.pageZoom = 1 }
    @objc private func showData() { NSWorkspace.shared.open(dataDirectory) }
    @objc private func showLog() { NSWorkspace.shared.open(dataDirectory.appendingPathComponent("desktop.log")) }
}

final class QuickEntryPanel: NSPanel {
    var onCancel: (() -> Void)?
    override var canBecomeKey: Bool { true }
    override func cancelOperation(_ sender: Any?) { onCancel?() }
}

@main
struct LocalPlannerApplication {
    static func main() {
        let application = NSApplication.shared
        let delegate = AppDelegate()
        application.setActivationPolicy(.regular)
        application.delegate = delegate
        withExtendedLifetime(delegate) { application.run() }
    }
}
