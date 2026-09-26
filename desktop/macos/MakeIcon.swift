import AppKit

let directory = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
for size in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let pixels = size * scale
        let image = NSImage(size: NSSize(width: pixels, height: pixels))
        image.lockFocus()
        let transform = AffineTransform(scale: CGFloat(pixels) / 1024)
        (transform as NSAffineTransform).concat()
        let tile = NSBezierPath(roundedRect: NSRect(x: 72, y: 72, width: 880, height: 880), xRadius: 198, yRadius: 198)
        let shadow = NSShadow()
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.2)
        shadow.shadowBlurRadius = 25
        shadow.shadowOffset = NSSize(width: 0, height: -8)
        NSGraphicsContext.saveGraphicsState()
        shadow.set()
        NSColor(calibratedRed: 0.96, green: 0.92, blue: 0.84, alpha: 1).setFill()
        tile.fill()
        NSGraphicsContext.restoreGraphicsState()
        NSGradient(starting: NSColor(calibratedRed: 1, green: 0.98, blue: 0.93, alpha: 1),
                   ending: NSColor(calibratedRed: 0.88, green: 0.81, blue: 0.68, alpha: 1))!.draw(in: tile, angle: -90)
        let card = NSBezierPath(roundedRect: NSRect(x: 208, y: 170, width: 608, height: 684), xRadius: 62, yRadius: 62)
        NSColor(calibratedRed: 1, green: 0.99, blue: 0.96, alpha: 1).setFill()
        card.fill()
        NSColor(calibratedRed: 0.55, green: 0.28, blue: 0.2, alpha: 1).setStroke()
        let header = NSBezierPath()
        header.lineWidth = 30
        header.lineCapStyle = .round
        header.move(to: NSPoint(x: 292, y: 737)); header.line(to: NSPoint(x: 728, y: 737)); header.stroke()
        for (index, y) in [CGFloat(591), 442, 293].enumerated() {
            let box = NSBezierPath(roundedRect: NSRect(x: 280, y: y - 39, width: 78, height: 78), xRadius: 17, yRadius: 17)
            box.lineWidth = 13
            if index == 0 {
                NSColor(calibratedRed: 0.55, green: 0.28, blue: 0.2, alpha: 1).setFill(); box.fill()
                NSColor.white.setStroke()
                let check = NSBezierPath()
                check.lineWidth = 11; check.lineCapStyle = .round; check.lineJoinStyle = .round
                check.move(to: NSPoint(x: 296, y: y)); check.line(to: NSPoint(x: 313, y: y - 15))
                check.line(to: NSPoint(x: 342, y: y + 18)); check.stroke()
            } else {
                NSColor(calibratedRed: 0.67, green: 0.58, blue: 0.44, alpha: 1).setStroke(); box.stroke()
            }
            NSColor(calibratedRed: 0.38, green: 0.32, blue: 0.25, alpha: index == 0 ? 0.4 : 0.85).setStroke()
            let line = NSBezierPath()
            line.lineWidth = 25; line.lineCapStyle = .round
            line.move(to: NSPoint(x: 419, y: y)); line.line(to: NSPoint(x: index == 2 ? 622 : 728, y: y)); line.stroke()
        }
        image.unlockFocus()
        let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
        let suffix = scale == 2 ? "@2x" : ""
        try bitmap.representation(using: .png, properties: [:])!.write(to: directory.appendingPathComponent("icon_\(size)x\(size)\(suffix).png"))
    }
}
