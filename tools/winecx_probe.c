/* Проверка 32-битного WoW64, x87 и создания устройства Direct3D 9. */
#define COBJMACROS
#include <windows.h>
#include <d3d9.h>
#include <stdio.h>
#include <math.h>

int main(void)
{
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
