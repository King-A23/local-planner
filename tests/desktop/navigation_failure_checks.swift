import Foundation

@main
struct NavigationFailureChecks {
    static func main() {
        let cases: [(String, NSError, Bool)] = [
            ("superseded request", NSError(domain: NSURLErrorDomain, code: NSURLErrorCancelled), true),
            ("frame policy interruption", NSError(domain: "WebKitErrorDomain", code: 102), true),
            ("connection failure", NSError(domain: NSURLErrorDomain, code: NSURLErrorCannotConnectToHost), false),
            ("unsupported URL", NSError(domain: "WebKitErrorDomain", code: 101), false),
            ("content process termination", NSError(domain: "WKErrorDomain", code: 2), false),
            ("same policy code in unrelated domain", NSError(domain: NSCocoaErrorDomain, code: 102), false),
            ("same cancellation code in unrelated domain", NSError(domain: NSCocoaErrorDomain, code: NSURLErrorCancelled), false),
            ("message alone is not sufficient", NSError(domain: NSURLErrorDomain, code: NSURLErrorCannotConnectToHost,
                userInfo: [NSLocalizedDescriptionKey: "Frame load interrupted"]), false),
        ]
        for (name, error, expected) in cases {
            precondition(NavigationFailure.isExpectedInterruption(error) == expected, name)
        }
        print("\(cases.count) navigation failure checks passed")
    }
}
