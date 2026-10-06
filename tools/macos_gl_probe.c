/* Независимая проверка графики macOS, без Wine и его библиотек. */
#include <OpenGL/OpenGL.h>
#include <stdio.h>

int main(void)
{
    CGLRendererInfoObj info = NULL;
    GLint count = 0, accelerated_count = 0;
    CGLError error = CGLQueryRendererInfo(~0u, &info, &count);
    if (error != kCGLNoError) {
        printf("Native CGL query failed: %s\n", CGLErrorString(error));
        return 1;
    }
    for (GLint i = 0; i < count; ++i) {
        GLint accelerated = 0, renderer = 0;
        if (CGLDescribeRenderer(info, i, kCGLRPAccelerated, &accelerated) != kCGLNoError)
            return 1;
        CGLDescribeRenderer(info, i, kCGLRPRendererID, &renderer);
        printf("Native CGL renderer: 0x%x accelerated=%d\n", renderer, accelerated);
        accelerated_count += !!accelerated;
    }
    CGLDestroyRendererInfo(info);
    if (!accelerated_count) {
        printf("Native CGL: no accelerated renderer available\n");
        return 77;
    }
    CGLPixelFormatAttribute attributes[] = {
        kCGLPFAAccelerated, kCGLPFAOpenGLProfile,
        (CGLPixelFormatAttribute)kCGLOGLPVersion_3_2_Core, 0
    };
    CGLPixelFormatObj format = NULL;
    CGLContextObj context = NULL;
    error = CGLChoosePixelFormat(attributes, &format, &count);
    if (error != kCGLNoError || !format) return 1;
    error = CGLCreateContext(format, NULL, &context);
    CGLDestroyPixelFormat(format);
    if (error != kCGLNoError || !context) return 1;
    CGLDestroyContext(context);
    printf("Native CGL accelerated context OK\n");
    return 0;
}
