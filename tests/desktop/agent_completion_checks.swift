import Foundation
import AppKit

final class CompletionFixture: URLProtocol {
    static var payload: Any = ["run": NSNull()]
    static var status = 200
    static var requests = 0
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        precondition(request.url?.absoluteString == "http://127.0.0.1:22788/api/agent-runs")
        precondition(request.httpMethod == "GET")
        Self.requests += 1
        let data = try! JSONSerialization.data(withJSONObject: Self.payload, options: [.fragmentsAllowed])
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.status,
                                                           httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@main
struct AgentCompletionChecks {
    static func run(_ id: String, _ status: String = "succeeded", result: Bool = true) -> [String: Any] {
        ["id": id, "status": status, "result": result ? ["receipt": ["changed": true]] : NSNull()]
    }

    static func pump(_ duration: TimeInterval = 0.12) {
        let deadline = Date().addingTimeInterval(duration)
        while Date() < deadline { RunLoop.main.run(until: Date().addingTimeInterval(0.01)) }
    }

    static func main() {
        if CommandLine.arguments.count == 2 {
            let app = NSApplication.shared
            app.setActivationPolicy(.prohibited)
            var completed = false
            let monitor = AgentCompletionMonitor(baseURL: URL(string: CommandLine.arguments[1])!, interval: 0.05,
                mainWindowReadable: { false }, updateBadge: { label in
                    app.dockTile.badgeLabel = label
                    if label == "1" {
                        precondition(app.dockTile.badgeLabel == "1")
                        completed = true
                    }
                })
            monitor.start()
            pump(0.4)
            print("MONITOR_READY"); fflush(stdout)
            let deadline = Date().addingTimeInterval(6)
            while !completed && Date() < deadline { pump(0.02) }
            monitor.stop()
            precondition(completed, "real backend completion must set Dock badge without any WebKit window")
            app.dockTile.badgeLabel = nil
            print("REAL_BACKEND_DOCK_BADGE_1")
            return
        }
        var checks = 0
        func check(_ value: @autoclosure () -> Bool, _ name: String) {
            precondition(value(), name)
            checks += 1
        }
        var badge = AgentCompletionBadge()
        badge.observe(run("old"), mainWindowReadable: false)
        check(badge.label == nil, "startup history is silent")
        badge.observe(run("old"), mainWindowReadable: false)
        check(badge.label == nil, "history stays silent")
        for status in ["starting", "running", "paused", "stopping"] {
            badge.observe(run("new", status, result: false), mainWindowReadable: false)
            check(badge.label == nil, "\(status) is not completed")
        }
        badge.observe(run("new"), mainWindowReadable: false)
        check(badge.label == "1", "background completion is unread")
        badge.observe(run("new"), mainWindowReadable: false)
        check(badge.label == "1", "polling does not duplicate")
        for status in ["failed", "failed_with_changes", "stopped", "stopped_with_changes"] {
            badge.observe(run(status, status), mainWindowReadable: false)
        }
        check(badge.label == "5", "all terminal outcomes can need attention")
        badge.acknowledge()
        check(badge.label == nil, "return to main window clears unread")
        badge.observe(run("new"), mainWindowReadable: false)
        check(badge.label == nil, "read completion is not replayed")
        badge.observe(run("foreground"), mainWindowReadable: true)
        check(badge.label == nil, "already visible result is read")
        badge.observe(run("incomplete", result: false), mainWindowReadable: false)
        check(badge.label == nil, "terminal without final result waits")
        badge.observe(run("incomplete"), mainWindowReadable: false)
        check(badge.label == "1", "final result completes pending snapshot")

        // Exercise the actual URLSession/timer monitor with no WebKit and no windows.
        // Prohibited activation policy ensures this executable never steals focus.
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        var readable = false
        var labels: [String?] = []
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [CompletionFixture.self]
        let monitor = AgentCompletionMonitor(baseURL: URL(string: "http://127.0.0.1:22788/")!,
            configuration: config, interval: 0.03, mainWindowReadable: { readable }, updateBadge: { label in
                labels.append(label)
                app.dockTile.badgeLabel = label
            })
        monitor.start(); pump()
        check(labels.isEmpty && CompletionFixture.requests > 0, "native monitor initializes without browser")
        CompletionFixture.payload = ["run": run("background", "paused", result: false)]
        pump()
        check(labels.isEmpty, "paused native run stays silent")
        CompletionFixture.payload = ["run": run("background")]
        pump()
        check(labels.count == 1 && labels.last! == "1" && app.dockTile.badgeLabel == "1",
              "native transport sets real NSDockTile badge")
        pump(0.2)
        check(labels.count == 1 && app.dockTile.badgeLabel == "1", "badge persists without five-second timer")
        monitor.acknowledge()
        check(app.dockTile.badgeLabel == "1", "settings/quick-entry/hidden main does not clear")
        readable = true; monitor.acknowledge()
        check(app.dockTile.badgeLabel == nil, "readable main clears native badge")
        readable = false
        CompletionFixture.payload = ["run": run("fast")]; pump()
        check(app.dockTile.badgeLabel == "1", "fast completion between polls is detected")
        CompletionFixture.status = 500
        CompletionFixture.payload = ["run": run("failure")]; pump()
        check(app.dockTile.badgeLabel == "1", "HTTP failure does not fabricate completion")
        CompletionFixture.status = 200
        CompletionFixture.payload = ["error": "bad snapshot"]; pump()
        check(app.dockTile.badgeLabel == "1", "malformed payload does not change unread state")
        CompletionFixture.payload = ["run": run("after-reconnect")]; pump()
        check(app.dockTile.badgeLabel == "2", "reconnected completion is counted once")
        readable = true; pump()
        check(app.dockTile.badgeLabel == nil, "main readable after modal dismissal clears even without key callback")
        readable = false
        CompletionFixture.payload = ["run": run("before-restore")]; pump()
        monitor.reset(); pump()
        check(app.dockTile.badgeLabel == nil, "restore clears stale badge and suppresses current history")
        monitor.stop(); pump()
        let requests = CompletionFixture.requests
        CompletionFixture.payload = ["run": run("after-stop")]; pump()
        check(CompletionFixture.requests == requests && app.dockTile.badgeLabel == nil, "stop cancels polling")
        print("\(checks) native completion checks passed")
    }
}
