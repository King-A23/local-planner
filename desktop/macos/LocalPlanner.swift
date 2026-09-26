import AppKit
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var backend: Process?
    private let lifetime = Pipe()
    private var output: Pipe?
    private var logFile: FileHandle?
    private var startupTimer: Timer?
    private var baseURL: URL?
    private var quitting = false
    private var failed = false

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
    }

    private func buildWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1320, height: 860),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Local Planner"
        window.minSize = NSSize(width: 900, height: 620)
        window.isReleasedWhenClosed = false
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
        add(app, "关于 Local Planner", #selector(NSApplication.orderFrontStandardAboutPanel(_:)))
        app.addItem(.separator())
        add(app, "隐藏 Local Planner", #selector(NSApplication.hide(_:)), "h")
        add(app, "显示全部", #selector(NSApplication.unhideAllApplications(_:)))
        app.addItem(.separator())
        add(app, "退出 Local Planner", #selector(NSApplication.terminate(_:)), "q")
        let file = menu("文件")
        add(file, "新增事项", #selector(quickAdd), "n", target: self)
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
        add(view, "今天", #selector(goToday), "1", target: self)
        add(view, "待办", #selector(goInventory), "2", target: self)
        add(view, "定期事项", #selector(goRecurrences), "3", target: self)
        view.addItem(.separator())
        add(view, "重新载入", #selector(reload), "r", target: self)
        add(view, "放大", #selector(zoomIn), "=", target: self)
        add(view, "缩小", #selector(zoomOut), "-", target: self)
        add(view, "实际大小", #selector(resetZoom), "0", target: self)
        let win = menu("窗口")
        add(win, "最小化", #selector(NSWindow.performMiniaturize(_:)), "m")
        add(win, "缩放", #selector(NSWindow.performZoom(_:)))
        NSApp.windowsMenu = win
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
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        webView = WKWebView(frame: window.contentView!.bounds, configuration: configuration)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.autoresizingMask = [.width, .height]
        webView.allowsBackForwardNavigationGestures = true
        window.contentView = webView
        webView.load(URLRequest(url: url))
        window.makeFirstResponder(webView)
    }

    private func isLocal(_ url: URL) -> Bool {
        url.scheme == baseURL?.scheme && url.host == baseURL?.host && url.port == baseURL?.port
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if isLocal(url) { decisionHandler(.allow); return }
        if navigationAction.navigationType == .linkActivated && ["https", "http", "mailto"].contains(url.scheme ?? "") {
            NSWorkspace.shared.open(url)
        }
        decisionHandler(.cancel)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, isLocal(url) { webView.load(URLRequest(url: url)) }
        return nil
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code != NSURLErrorCancelled { showFailure("页面加载失败：\(error.localizedDescription)") }
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { webView.reload() }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "确定")
        alert.addButton(withTitle: "取消")
        alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.beginSheetModal(for: window) { _ in completionHandler() }
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

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window?.makeKeyAndOrderFront(nil)
        return true
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if quitting { return .terminateLater }
        quitting = true
        startupTimer?.invalidate()
        try? lifetime.fileHandleForWriting.close()
        guard let process = backend, process.isRunning else { return .terminateNow }
        // EOF triggers backend cleanup, including any agent process groups.
        DispatchQueue.main.asyncAfter(deadline: .now() + 10) {
            if process.isRunning { kill(process.processIdentifier, SIGKILL) }
            NSApp.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }

    private func navigate(_ path: String) {
        guard let baseURL else { return }
        webView?.load(URLRequest(url: baseURL.appendingPathComponent(path)))
    }
    @objc private func quickAdd() {
        webView?.evaluateJavaScript("document.querySelector('.add-form input, .inventory-add-form input') !== null") { [weak self] result, _ in
            if result as? Bool == true {
                self?.webView?.evaluateJavaScript("window.dispatchEvent(new Event('planner:quick-add'))")
            } else if let url = self?.baseURL {
                self?.webView?.load(URLRequest(url: url.appending(queryItems: [URLQueryItem(name: "add", value: "1")])))
            }
        }
    }
    @objc private func goToday() { navigate("") }
    @objc private func goInventory() { navigate("inventory") }
    @objc private func goRecurrences() { navigate("recurrences") }
    @objc private func reload() { webView?.reload() }
    @objc private func zoomIn() { if let webView { webView.pageZoom = min(2, webView.pageZoom + 0.1) } }
    @objc private func zoomOut() { if let webView { webView.pageZoom = max(0.6, webView.pageZoom - 0.1) } }
    @objc private func resetZoom() { webView?.pageZoom = 1 }
    @objc private func showData() { NSWorkspace.shared.open(dataDirectory) }
    @objc private func showLog() { NSWorkspace.shared.open(dataDirectory.appendingPathComponent("desktop.log")) }
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.setActivationPolicy(.regular)
application.delegate = delegate
application.run()
