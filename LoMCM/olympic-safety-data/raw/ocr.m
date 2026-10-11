#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#import <Vision/Vision.h>

int main(int argc, char** argv) {
  @autoreleasepool {
    if (argc < 2) { fprintf(stderr,"usage: ocr <image>\n"); return 1; }
    NSString *path = [NSString stringWithUTF8String:argv[1]];
    NSImage *img = [[NSImage alloc] initWithContentsOfFile:path];
    if (!img) { fprintf(stderr,"cannot load %s\n", argv[1]); return 1; }
    CGImageRef cg = [img CGImageForProposedRect:NULL context:nil hints:nil];
    VNRecognizeTextRequest *req = [[VNRecognizeTextRequest alloc] init];
    req.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
    req.usesLanguageCorrection = NO;
    VNImageRequestHandler *h = [[VNImageRequestHandler alloc] initWithCGImage:cg options:@{}];
    NSError *err = nil;
    [h performRequests:@[req] error:&err];
    if (err) { fprintf(stderr,"err: %s\n", err.description.UTF8String); return 1; }
    for (VNRecognizedTextObservation *obs in req.results) {
      VNRecognizedText *t = [[obs topCandidates:1] firstObject];
      CGRect b = obs.boundingBox;
      printf("%.3f\t%.3f\t%.3f\t%.3f\t%s\n", b.origin.x, b.origin.y, b.size.width, b.size.height, t.string.UTF8String);
    }
  }
  return 0;
}
