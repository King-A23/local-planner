import Foundation

enum NavigationFailure {
    static func isExpectedInterruption(_ error: Error) -> Bool {
        let failure = error as NSError
        if failure.domain == NSURLErrorDomain && failure.code == NSURLErrorCancelled {
            return true
        }
        // WebKitErrors.h: WebKitErrorFrameLoadInterruptedByPolicyChange (102).
        // WKWebView still emits this legacy-domain error when a newer navigation
        // or a download policy interrupts a frame load.
        return failure.domain == "WebKitErrorDomain" && failure.code == 102
    }
}
