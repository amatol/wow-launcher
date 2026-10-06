/* Проверка 32-битного WoW64, x87 и создания устройства Direct3D 9. */
#define COBJMACROS
#include <windows.h>
#include <d3d9.h>
#include <stdio.h>
#include <math.h>

/* Все сочетания RPL и оба исходных значения ZF. Проверяем остальные
 * арифметические флаги, старшие биты EAX и неизменность EDX. */
static int check_arpl(void)
{
    unsigned int dst, src, zf;
    for (dst = 0; dst < 4; ++dst)
    for (src = 0; src < 4; ++src)
    for (zf = 0; zf < 2; ++zf)
    {
        unsigned int a = 0x878a62a8 | dst, d = 0x1054dd04 | src;
        unsigned int before = 0xA97 | (zf << 6), after;
        unsigned int expected = (a & ~3u) | (dst < src ? src : dst);
        __asm__ volatile ("pushl %[flags]\n\tpopfl\n\t.byte 0x63, 0xd0\n\tpushfl\n\tpopl %[after]"
                          : "+a"(a), "+d"(d), [after] "=r"(after)
                          : [flags] "r"(before) : "cc", "memory");
        if (a != expected || d != (0x1054dd04 | src) ||
            (after & 0x8d5) != ((before & 0x895) | (dst < src ? 0x40 : 0)))
        {
            printf("ARPL failed dst=%u src=%u zf=%u eax=%08x edx=%08x flags=%08x\n",
                   dst, src, zf, a, d, after);
            return 16;
        }
    }
    printf("32-bit ARPL OK (32 cases, including crash registers)\n");
    fflush(stdout);
    return 0;
}

int main(void)
{
    if (check_arpl()) return 16;
    volatile double a = 1.25, b = 2.5;
    volatile double result = a * b + a;
    if (fabs(result - 4.375) > 0.000001) return 10;
    printf("32-bit x87 OK\n");
    HWND window = CreateWindowA("STATIC", "Dreamworld WineCX probe", WS_OVERLAPPEDWINDOW,
                               0, 0, 640, 480, NULL, NULL, GetModuleHandle(NULL), NULL);
    if (!window) return 11;
    IDirect3D9 *d3d = Direct3DCreate9(D3D_SDK_VERSION);
    if (!d3d) return 12;
    D3DADAPTER_IDENTIFIER9 adapter;
    if (FAILED(IDirect3D9_GetAdapterIdentifier(d3d, 0, 0, &adapter))) return 13;
    printf("D3D9 adapter: %s\n", adapter.Description);
    D3DPRESENT_PARAMETERS pp = {0};
    pp.Windowed = TRUE;
    pp.SwapEffect = D3DSWAPEFFECT_DISCARD;
    pp.hDeviceWindow = window;
    IDirect3DDevice9 *device = NULL;
    HRESULT hr = IDirect3D9_CreateDevice(d3d, 0, D3DDEVTYPE_HAL, window,
                                        D3DCREATE_SOFTWARE_VERTEXPROCESSING, &pp, &device);
    if (FAILED(hr)) { printf("CreateDevice failed: %08lx\n", (unsigned long)hr); return 14; }
    IDirect3DDevice9_Clear(device, 0, NULL, D3DCLEAR_TARGET, 0xff224466, 1.0f, 0);
    hr = IDirect3DDevice9_Present(device, NULL, NULL, NULL, NULL);
    IDirect3DDevice9_Release(device);
    IDirect3D9_Release(d3d);
    DestroyWindow(window);
    if (FAILED(hr)) return 15;
    printf("32-bit Direct3D 9 device + Present OK\n");
    return 0;
}
