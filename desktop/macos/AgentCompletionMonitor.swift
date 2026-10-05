import Foundation

// Session-only unread state. A completed startup snapshot is history, not a new alert.
struct AgentCompletionBadge {
    private var initialized = false
    private var completed: [String] = []
    private(set) var unreadCount = 0
    var label: String? { unreadCount == 0 ? nil : String(unreadCount) }

    mutating func observe(_ run: [String: Any]?, mainWindowReadable: Bool) {
        let initial = !initialized
        initialized = true
        guard let run, let id = run["id"] as? String, let status = run["status"] as? String,
              ["succeeded", "failed", "failed_with_changes", "stopped", "stopped_with_changes"].contains(status),
              run["result"] is [String: Any], !completed.contains(id) else { return }
        completed.append(id)
        if completed.count > 100 { completed.removeFirst() }
        if !initial && !mainWindowReadable { unreadCount += 1 }
    }

    mutating func acknowledge() { unreadCount = 0 }
}

// Native polling continues when WebKit is hidden, closed or throttling JavaScript.
// Only GETs the owned backend; never starts an agent or writes plan data.
final class AgentCompletionMonitor {
    private let url: URL
    private let session: URLSession
    private let mainWindowReadable: () -> Bool
    private let updateBadge: (String?) -> Void
    private let interval: TimeInterval
    private var timer: Timer?
    private var task: URLSessionDataTask?
    private var generation = 0
    private var activity: NSObjectProtocol?
    private var badge = AgentCompletionBadge()

    init(baseURL: URL, configuration: URLSessionConfiguration = .ephemeral,
         interval: TimeInterval = 1, mainWindowReadable: @escaping () -> Bool,
         updateBadge: @escaping (String?) -> Void) {
        precondition(baseURL.scheme == "http" && baseURL.host == "127.0.0.1")
        url = baseURL.appendingPathComponent("api/agent-runs")
        configuration.timeoutIntervalForRequest = 5
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        session = URLSession(configuration: configuration)
        self.interval = interval
        self.mainWindowReadable = mainWindowReadable
        self.updateBadge = updateBadge
    }

    func start() {
        guard timer == nil else { return }
        let timer = Timer(timeInterval: interval, repeats: true) { [weak self] _ in self?.poll() }
        self.timer = timer
        RunLoop.main.add(timer, forMode: .common)
        poll()
    }

    func stop() {
        generation += 1
        timer?.invalidate()
        timer = nil
        task?.cancel()
        task = nil
        setExecuting(false)
    }

    func reset() {
        stop()
        badge = AgentCompletionBadge()
        updateBadge(nil)
        start()
    }

    func acknowledge() {
        guard mainWindowReadable() else { return }
        badge.acknowledge()
        updateBadge(nil)
    }

    private func poll() {
        guard timer != nil, task == nil else { return }
        let expectedGeneration = generation
        task = session.dataTask(with: url) { [weak self] data, response, error in
            DispatchQueue.main.async {
                guard let self, self.generation == expectedGeneration, self.timer != nil else { return }
                self.task = nil
                guard error == nil, (response as? HTTPURLResponse)?.statusCode == 200,
                      let data, let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      payload.keys.contains("run"),
                      payload["run"] is NSNull || payload["run"] is [String: Any] else { return }
                let run = payload["run"] as? [String: Any]
                let executing = ["starting", "running", "paused", "stopping"].contains(run?["status"] as? String ?? "")
                self.setExecuting(executing)
                let previous = self.badge.label
                let readable = self.mainWindowReadable()
                self.badge.observe(run, mainWindowReadable: readable)
                // Also cover a sheet finishing after the key-window callback.
                if readable { self.badge.acknowledge() }
                if previous != self.badge.label { self.updateBadge(self.badge.label) }
            }
        }
        task?.resume()
    }

    private func setExecuting(_ executing: Bool) {
        if executing && activity == nil {
            // Keep completion checks timely while allowing normal system sleep.
            activity = ProcessInfo.processInfo.beginActivity(options: .userInitiatedAllowingIdleSystemSleep,
                                                            reason: "监测计划助手执行完成")
        } else if !executing, let activity {
            ProcessInfo.processInfo.endActivity(activity)
            self.activity = nil
        }
    }

    deinit {
        timer?.invalidate()
        task?.cancel()
        if let activity { ProcessInfo.processInfo.endActivity(activity) }
        session.invalidateAndCancel()
    }
}
