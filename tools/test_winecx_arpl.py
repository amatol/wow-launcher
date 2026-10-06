#!/usr/bin/env python3
"""Проверить настоящий C-обработчик из патча без зависимости от macOS SDK."""
from pathlib import Path
import subprocess
import tempfile

patch = Path(__file__).with_name('patches').joinpath('winecx-arpl.patch').read_text()
added = '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
helper = added[added.index('static inline BOOL emulate_arpl_register'):added.index('\n}', added.index('static inline BOOL emulate_arpl_register')) + 2]
preamble = '''
#include <assert.h>
#include <stdint.h>
#include <string.h>
typedef int BOOL;
typedef unsigned char BYTE;
typedef uint64_t ULONGLONG;
#define TRUE 1
#define FALSE 0
typedef struct { uint64_t regs[8], rip, flags; } ucontext_t;
typedef struct { uint64_t Rip; unsigned short SegCs; } CONTEXT;
static unsigned short cs32_sel = 0x107;
static unsigned int readable = 2;
static unsigned int virtual_uninterrupted_read_memory(const BYTE *src, BYTE *dst, unsigned int n)
{ if (n > readable) n = readable; memcpy(dst, src, n); return n; }
#define RIP_sig(c) ((c)->rip)
#define EFL_sig(c) ((c)->flags)
'''
for i, reg in enumerate(('RAX','RCX','RDX','RBX','RSP','RBP','RSI','RDI')):
    preamble += f'#define {reg}_sig(c) ((c)->regs[{i}])\n'
main = '''
int main(void)
{
    BYTE code[2] = {0x63, 0xd0};
    CONTEXT context = {(uintptr_t)code, 0x107};
    unsigned int src, dst, srpl, drpl, zf, j;
    for (src=0; src<8; src++) for (dst=0; dst<8; dst++)
    for (srpl=0; srpl<4; srpl++) for (drpl=0; drpl<4; drpl++)
    for (zf=0; zf<2; zf++)
    {
        ucontext_t c = {{0}, 0x59b4360, 0x200a97 | (zf << 6)}, expected;
        for (j=0; j<8; j++) c.regs[j]=0xfedcba98878a62a8ULL + (j<<8);
        c.regs[src] |= srpl;
        c.regs[dst] = (c.regs[dst] & ~3ULL) | drpl;
        expected=c;
        if ((c.regs[dst]&3) < (c.regs[src]&3))
        {
            expected.regs[dst]=(c.regs[dst]&~3ULL)|(c.regs[src]&3);
            expected.flags |= 0x40;
        }
        else expected.flags &= ~0x40ULL;
        expected.rip+=2;
        code[1]=0xc0|(src<<3)|dst;
        assert(emulate_arpl_register(&c,&context));
        assert(!memcmp(&c,&expected,sizeof(c)));
    }
    /* Любая форма кроме unprefixed reg/reg и режим 64 бит остаются Wine. */
    for (j=0;j<256;j++)
    {
        ucontext_t c={{0},1234,0x246}, before=c;
        code[0]=j; code[1]=0xd0;
        if (j==0x63) continue;
        assert(!emulate_arpl_register(&c,&context));
        assert(!memcmp(&c,&before,sizeof(c)));
    }
    code[0]=0x63;
    for (j=0;j<192;j++)
    {
        ucontext_t c={{0},1234,0x246}, before=c;
        code[1]=j;
        assert(!emulate_arpl_register(&c,&context));
        assert(!memcmp(&c,&before,sizeof(c)));
    }
    code[1]=0xd0;
    for (j=0;j<3;j++)
    {
        ucontext_t c={{0},1234,0x246}, before=c;
        context.SegCs=j==2?0x2b:0x107;
        readable=j==2?2:j;
        assert(!emulate_arpl_register(&c,&context));
        assert(!memcmp(&c,&before,sizeof(c)));
    }
    return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / 'arpl.c'
    executable = Path(directory) / 'arpl'
    source.write_text(preamble + helper + main)
    subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-O2', str(source), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
print('ARPL handler: 2048 register/flags cases and 450 rejection cases PASS')
