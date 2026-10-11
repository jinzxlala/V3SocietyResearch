import Foundation
import Vision
import AppKit

let path = CommandLine.arguments[1]
guard let img = NSImage(contentsOfFile: path),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("cannot load image\n".data(using:.utf8)!); exit(1)
}
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.usesLanguageCorrection = false
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
try handler.perform([req])
for obs in (req.results ?? []) {
    if let c = obs.topCandidates(1).first {
        let b = obs.boundingBox
        print(String(format: "%.3f\t%.3f\t%.3f\t%.3f\t%@", b.minX, b.minY, b.width, b.height, c.string))
    }
}
