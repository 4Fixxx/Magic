#!/usr/bin/env python3
"""magicc - Magic language compiler (.mmx -> .cmc)

usage: magicc.py prog.mmx [-o prog.cmc] [--exit halt|ret|reboot] [--no-clear] [--pad]

OUTPUT   raw flat 32-bit x86 machine code, no header, fully position independent.
ENTRY    byte 0. Run in 32-bit protected mode, ring 0, flat segments (CS/DS/ES/SS
         same base, normally 0, limit 4GB). Interrupts are never enabled by the code.
MEMORY   program needs BSS right after the image (size printed after compile),
         it zeroes it itself and uses its own stack inside it. --pad appends the
         zeros to the file instead (for loaders that load exactly file size).
SCREEN   VGA colour text 80x25 at 0xB8000, hardware cursor via 0x3D4/0x3D5.
         every print ends with a newline, scrolls at the bottom. CP437 text.
KEYS     PS/2 polled (status 0x64, data 0x60), scancode set 1 (BIOS translated).
         <a>-<z> <0>-<9> <space> <enter> <esc> <tab> <backspace> <up> <down>
         <left> <right> <f1>-<f12> and - = [ ] ; ' ` \\ , . /
         input is polled continuously (after every statement) + at jump/return/loop end/halt/#end.
         keys pressed while a function runs are queued (16 deep, the 17th is dropped).
PORTS    16 bit ISA style port I/O (ports 0-65535, data 0-65535, 'in ax,dx' / 'out dx,ax').
         output <port>, <data>     writes <data> to <port>. register operands use their low 16 bits.
         on port input <port>, <reg>   port function: polled the same way as keys, fires only when
                                       the port inputs something: a NEW NON-ZERO value (idle is 0, going
                                       back to 0 never fires). Stores the value in <reg> (even with no
                                       code under it), then runs its code.
         on port input <port>, "N"     fires its code only when the new value is N (N is 1..65535, 0 is
                                       "no input" so it is a compile error), stores nothing.
         <port> is a plain number or a register (its low 16 bits, read every poll).
         port events are queued (16 deep) while a function runs, same as keys.
SIMULTANEOUS  events found in the same poll count as "exactly at the same time". When 2 or more
         functions are triggered together the order is random: key vs port (random pick between the
         two queue heads when they were found in the same poll, older events always go first),
         port vs port (the events of one poll are shuffled), and several functions on the same key
         (random one goes first).
RULES    - custom names ($NAME$) are global and resolved at compile time.
         - jump pushes a return point on a 64-deep ring (oldest dropped when full),
           return with an empty ring does nothing.
         - skip #x sets a flag: falling into #x from above jumps past it, jump #x still enters it.
         - inside @function / !<cmd>: 'return' leaves that function/command,
           'jump' abandons it (stack unwound) and continues at the section, no return point.
         - loop: body runs, at ']' c moves 1 toward 0, repeats while c != 0.
         - the else line may be at the same or deeper indent than its if.
         - tab counts as 4 spaces. numbers: decimal only (hex like 0x8 is an error).
"""
import sys
import os
import re
import argparse

MAXV = 2147483647
EAX, ECX, EDX, EBX, ESP, EBP, ESI, EDI = range(8)
CC_B, CC_AE, CC_E, CC_NE, CC_S, CC_NS, CC_G = 2, 3, 4, 5, 8, 9, 0xF

REG4 = {'a': 0, 'b': 4, 'c': 8, 'd': 12}
HEX_RE = re.compile(r'[+-]?0[xX][0-9a-fA-F]+')
NUM_RE = re.compile(r'[+-]?[0-9]+')
MEM0 = 16
BUILTIN = {'add', 'sub', 'mul', 'div', 'move', 'setname', 'copy', 'jump', 'print', 'if', 'exit',
           'stackadd', 'stack2add', 'stacktake', 'stack2take', 'return', 'random', 'nop',
           'compare', 'skip', 'halt', 'resume', 'output', 'else'}

KEYS = {'esc': 0x01, '-': 0x0C, '=': 0x0D, 'backspace': 0x0E, 'tab': 0x0F, '[': 0x1A, ']': 0x1B,
        'enter': 0x1C, ';': 0x27, "'": 0x28, '`': 0x29, '\\': 0x2B, ',': 0x33, '.': 0x34,
        '/': 0x35, 'space': 0x39, 'up': 0x148, 'down': 0x150, 'left': 0x14B, 'right': 0x14D,
        'f11': 0x57, 'f12': 0x58}
for _i, _ch in enumerate('1234567890'):
    KEYS[_ch] = 0x02 + _i
for _i, _ch in enumerate('qwertyuiop'):
    KEYS[_ch] = 0x10 + _i
for _i, _ch in enumerate('asdfghjkl'):
    KEYS[_ch] = 0x1E + _i
for _i, _ch in enumerate('zxcvbnm'):
    KEYS[_ch] = 0x2C + _i
for _i in range(1, 11):
    KEYS['f%d' % _i] = 0x3A + _i


# ---------------------------------------------------------------- assembler
class Asm:
    def __init__(s):
        s.b = bytearray()
        s.lab = {}
        s.fix = []
        s.n = 0

    def new(s, p='L'):
        s.n += 1
        return '%s%d' % (p, s.n)

    def label(s, name):
        assert name not in s.lab, name
        s.lab[name] = len(s.b)

    def raw(s, *xs):
        s.b.extend(xs)

    def dd(s, v):
        s.b.extend((v & 0xFFFFFFFF).to_bytes(4, 'little'))

    def fx(s, kind, arg):
        s.fix.append((len(s.b), kind, arg))
        s.dd(0)

    def modrm(s, r, m):
        k = m[0]
        if k == 'bss':
            s.raw(0x80 | (r << 3) | 5)
            s.fx('bss', m[1])
        elif k == 'bssx':
            sc = {1: 0, 2: 1, 4: 2, 8: 3}[m[3]]
            s.raw(0x80 | (r << 3) | 4, (sc << 6) | (m[2] << 3) | 5)
            s.fx('bss', m[1])
        elif k == 'lbl':
            s.raw(0x80 | (r << 3) | 5)
            s.fx('lbl', m[1])
        elif k == 'lblx':
            sc = {1: 0, 2: 1, 4: 2, 8: 3}[m[3]]
            s.raw(0x80 | (r << 3) | 4, (sc << 6) | (m[2] << 3) | 5)
            s.fx('lbl', m[1])
        elif k == 'r':
            s.raw((r << 3) | m[1])
        elif k == 'rd':
            s.raw(0x80 | (r << 3) | m[1])
            s.dd(m[2])
        else:
            raise ValueError(k)

    def resolve(s, bss0):
        for pos, kind, arg in s.fix:
            if kind == 'rel':
                v = s.lab[arg] - (pos + 4)
            elif kind == 'lbl':
                v = s.lab[arg]
            else:
                v = bss0 + arg
            s.b[pos:pos + 4] = (v & 0xFFFFFFFF).to_bytes(4, 'little')

    # mov / lea
    def mov_rm(s, r, m): s.raw(0x8B); s.modrm(r, m)
    def mov_mr(s, m, r): s.raw(0x89); s.modrm(r, m)
    def mov_mi(s, m, v): s.raw(0xC7); s.modrm(0, m); s.dd(v)
    def mov_m8i(s, m, v): s.raw(0xC6); s.modrm(0, m); s.raw(v & 255)
    def mov_ri(s, r, v): s.raw(0xB8 + r); s.dd(v)
    def mov_rl(s, r, name): s.raw(0xB8 + r); s.fx('lbl', name)
    def mov_rr(s, d, x): s.raw(0x89, 0xC0 | (x << 3) | d)
    def lea(s, r, m): s.raw(0x8D); s.modrm(r, m)
    # alu reg, mem
    def add_rm(s, r, m): s.raw(0x03); s.modrm(r, m)
    def sub_rm(s, r, m): s.raw(0x2B); s.modrm(r, m)
    def cmp_rm(s, r, m): s.raw(0x3B); s.modrm(r, m)
    def xor_rm(s, r, m): s.raw(0x33); s.modrm(r, m)
    def or_rm(s, r, m): s.raw(0x0B); s.modrm(r, m)
    def imul_rm(s, r, m): s.raw(0x0F, 0xAF); s.modrm(r, m)
    # alu reg, imm
    def add_ri(s, r, v): s.raw(0x81, 0xC0 | r); s.dd(v)
    def sub_ri(s, r, v): s.raw(0x81, 0xE8 | r); s.dd(v)
    def and_ri(s, r, v): s.raw(0x81, 0xE0 | r); s.dd(v)
    def cmp_ri(s, r, v): s.raw(0x81, 0xF8 | r); s.dd(v)
    def cmp_mi(s, m, v): s.raw(0x81); s.modrm(7, m); s.dd(v)
    def cmp_m8i(s, m, v): s.raw(0x80); s.modrm(7, m); s.raw(v & 255)
    def test_ri(s, r, v): s.raw(0xF7, 0xC0 | r); s.dd(v)
    def imul_rri(s, d, x, v): s.raw(0x69, 0xC0 | (d << 3) | x); s.dd(v)
    # reg, reg
    def test_rr(s, a, b): s.raw(0x85, 0xC0 | (b << 3) | a)
    def xor_rr(s, a, b): s.raw(0x31, 0xC0 | (b << 3) | a)
    def add_rr(s, d, x): s.raw(0x01, 0xC0 | (x << 3) | d)
    # single reg
    def neg(s, r): s.raw(0xF7, 0xD8 | r)
    def inc(s, r): s.raw(0x40 + r)
    def dec(s, r): s.raw(0x48 + r)
    def shl(s, r, n): s.raw(0xC1, 0xE0 | r, n)
    def shr(s, r, n): s.raw(0xC1, 0xE8 | r, n)
    def div(s, r): s.raw(0xF7, 0xF0 | r)
    def idiv(s, r): s.raw(0xF7, 0xF8 | r)
    def movzx8(s, d, x): s.raw(0x0F, 0xB6, 0xC0 | (d << 3) | x)
    def movzx16(s, d, x): s.raw(0x0F, 0xB7, 0xC0 | (d << 3) | x)
    def push(s, r): s.raw(0x50 + r)
    def pop(s, r): s.raw(0x58 + r)
    def push_m(s, m): s.raw(0xFF); s.modrm(6, m)
    def pop_m(s, m): s.raw(0x8F); s.modrm(0, m)
    # flow
    def call(s, l): s.raw(0xE8); s.fx('rel', l)
    def jmp(s, l): s.raw(0xE9); s.fx('rel', l)
    def jcc(s, cc, l): s.raw(0x0F, 0x80 + cc); s.fx('rel', l)
    def call_r(s, r): s.raw(0xFF, 0xD0 | r)
    def jmp_r(s, r): s.raw(0xFF, 0xE0 | r)


class Bss:
    def __init__(self):
        self.size = 0
        self.o = {}

    def alloc(self, name, n):
        self.o[name] = self.size
        self.size += (n + 3) & ~3
        return self.o[name]


# ---------------------------------------------------------------- front end
class Line:
    def __init__(self, no, indent, text):
        self.no = no
        self.indent = indent
        self.text = text


class N:
    def __init__(self, k, no, **kw):
        self.k = k
        self.no = no
        self.__dict__.update(kw)


class Compiler:
    def __init__(self, src):
        self.src = src.split('\n')
        self.errs = []
        self.names = {}
        self.regname = {}
        self.custom = set()
        self.cmds = []
        self.funcs = []
        self.pfuncs = []
        self.secs = ['start']
        self.refs = []
        self.skipped = set()
        self.main = []
        self.L = []
        self.p = 0

    def err(self, no, msg):
        self.errs.append((no, msg))

    # ---- lexing
    def lex(self):
        out = []
        for no, raw in enumerate(self.src, 1):
            raw = raw.rstrip('\r')
            i = 0
            ind = 0
            while i < len(raw) and raw[i] in ' \t':
                ind += 4 if raw[i] == '\t' else 1
                i += 1
            body = raw[i:]
            inq = False
            cut = None
            for j, ch in enumerate(body):
                if ch == '"':
                    inq = not inq
                elif ch == '~' and not inq:
                    if j > 0 and body[j - 1] not in ' \t':
                        self.err(no, "comment '~' must have a space or tab before it")
                    cut = j
                    break
            if cut is not None:
                body = body[:cut]
            body = body.rstrip()
            if body:
                out.append(Line(no, ind, body))
        return out

    def split(self, text, no, quiet=False):
        out = []
        cur = []
        inq = False
        for ch in text:
            if ch == '"':
                inq = not inq
                cur.append(ch)
            elif ch == ';' and not inq:
                out.append(''.join(cur).strip())
                cur = []
            else:
                cur.append(ch)
        out.append(''.join(cur).strip())
        if inq:
            if not quiet:
                self.err(no, 'unterminated string (missing closing quote)')
            return None
        if any(x == '' for x in out):
            if not quiet:
                self.err(no, "empty command (stray ';')")
            return None
        return out

    # ---- operands
    def regref(self, tok, no, allow_names=True):
        if tok in REG4:
            return ('reg', REG4[tok])
        if tok in ('e', 'f'):
            self.err(no, "'%s' is a stack and cannot be an operand (use stackadd/stacktake)" % tok)
            return None
        m = re.fullmatch(r'm(0|[1-9][0-9]*)', tok)
        if m:
            k = int(m.group(1))
            if 1 <= k <= 4096:
                return ('reg', MEM0 + (k - 1) * 4)
            self.err(no, "memory register '%s' out of range (m1..m4096)" % tok)
            return None
        m = re.fullmatch(r'\$([A-Z]+)\$', tok)
        if m and allow_names:
            if m.group(1) in self.names:
                return ('reg', self.names[m.group(1)])
            self.err(no, "unknown custom name '%s' (never set with setname)" % tok)
            return None
        if HEX_RE.fullmatch(tok):
            self.err(no, "hex numbers are not allowed ('%s'), use a decimal number" % tok)
            return None
        self.err(no, "invalid operand '%s'" % tok)
        return None

    def need_reg(self, tok, no, what='first operand'):
        if NUM_RE.fullmatch(tok):
            self.err(no, "%s must be a register, got number '%s'" % (what, tok))
            return None
        return self.regref(tok, no)

    def operand(self, tok, no):
        if NUM_RE.fullmatch(tok):
            v = int(tok, 10)
            if v > MAXV or v < -MAXV:
                self.err(no, "number %s out of range (%d..%d)" % (tok, -MAXV, MAXV))
                return None
            return ('num', v)
        return self.regref(tok, no)

    def args(self, rest, no, cmd):
        if rest == '':
            self.err(no, "'%s' needs operands" % cmd)
            return None
        toks = [t.strip() for t in rest.split(',')]
        if any(t == '' for t in toks):
            self.err(no, "empty operand (stray ',')")
            return None
        return toks

    # ---- setname pre-pass
    def scan_setname(self, s, no):
        rest = s[len('setname'):].strip()
        toks = [t.strip() for t in rest.split(',')]
        if len(toks) != 2:
            self.err(no, "syntax: setname <register>, <NAME>")
            return
        if toks[0].startswith('$'):
            self.err(no, "register already has a custom name (a register can have only 1 custom name)")
            return
        r = self.regref(toks[0], no, False)
        if r is None:
            return
        m = re.fullmatch(r'<([A-Z]+)>', toks[1])
        if not m:
            self.err(no, "custom name must be CAPITAL letters only inside < >, got '%s'" % toks[1])
            return
        nm = m.group(1)
        off = r[1]
        if off in self.regname and self.regname[off] != nm:
            self.err(no, "register already has custom name $%s$ (a register can have only 1 custom name)" % self.regname[off])
            return
        if nm in self.names and self.names[nm] != off:
            self.err(no, "custom name $%s$ is already used for another register" % nm)
            return
        self.names[nm] = off
        self.regname[off] = nm

    # ---- driver
    def compile(self):
        L = self.lex()
        if not L:
            self.err(1, "empty program: expected '#start' ... '#end'")
            return
        if L[0].text != '#start':
            self.err(L[0].no, "program must begin with '#start'")
            return
        ends = [i for i, l in enumerate(L) if l.text == '#end']
        if not ends:
            self.err(L[-1].no, "missing '#end'")
            return
        e = ends[0]
        main, rest = L[1:e], L[e + 1:]
        for ln in rest:
            if ln.text[0] == '!':
                m = re.fullmatch(r'!<([A-Za-z]+)>', ln.text)
                if not m:
                    self.err(ln.no, "invalid custom command definition, expected !<name> (letters only)")
                elif m.group(1) in BUILTIN:
                    self.err(ln.no, "custom command name '%s' is a reserved word" % m.group(1))
                elif m.group(1) in self.custom:
                    self.err(ln.no, "custom command '%s' defined twice" % m.group(1))
                else:
                    self.custom.add(m.group(1))
        for ln in main + rest:
            if ln.text[0] in '#@!':
                continue
            ss = self.split(ln.text, ln.no, True)
            for s in (ss or []):
                if s.split(None, 1)[0] == 'setname':
                    self.scan_setname(s, ln.no)
        self.L = main
        self.p = 0
        body = self.region(L[0].indent, True)
        self.main = [N('section', L[0].no, name='start')] + body
        self.parse_rest(rest)
        for kind, nm, no in self.refs:
            if kind == 'jump':
                if nm != 'end' and nm not in self.secs:
                    self.err(no, "jump to unknown section '#%s'" % nm)
            else:
                if nm not in self.secs:
                    self.err(no, "skip of unknown section '#%s'" % nm)
                else:
                    self.skipped.add(nm)

    # ---- structure parsing
    def region(self, indent, top):
        out = []
        while True:
            out += self.parse_stmts(indent, top)
            if self.p >= len(self.L):
                break
            ln = self.L[self.p]
            self.p += 1
            if ln.text == 'else':
                self.err(ln.no, "'else' without matching 'if'")
            elif ln.text[0] == '#':
                self.err(ln.no, "section header not allowed here (only in main code, outside if/else and loops)")
            else:
                self.err(ln.no, "inconsistent indentation")
        return self.structure(out)

    def skip_region(self, ln):
        L = self.L
        while self.p < len(L):
            n = L[self.p]
            if n.text[0] == '#':
                break
            if n.indent > ln.indent or (n.text == 'else' and n.indent >= ln.indent):
                self.p += 1
            else:
                break

    def parse_stmts(self, indent, top):
        L = self.L
        out = []
        while self.p < len(L):
            ln = L[self.p]
            t = ln.text
            if t == 'else':
                break
            if t[0] == '#':
                if not top:
                    break
                self.p += 1
                n = self.section(ln)
                if n:
                    out.append(n)
                continue
            if ln.indent < indent:
                break
            self.p += 1
            if ln.indent > indent:
                self.err(ln.no, "unexpected indentation (indent is only used for code under if/else)")
                continue
            if t[0] in '@!':
                self.err(ln.no, "functions and custom commands must be defined after '#end'")
                self.skip_region(ln)
                continue
            ss = self.split(t, ln.no)
            if ss is None:
                continue
            for k, s in enumerate(ss):
                if s.split(None, 1)[0] == 'if':
                    node = self.parse_if_head(s, ln)
                    if node is not None and k != len(ss) - 1:
                        self.err(ln.no, "'if' must be the last command on its line")
                        node = None
                    if node is None:
                        self.skip_region(ln)
                    else:
                        self.parse_if_body(node, ln)
                        out.append(node)
                    continue
                if s == '[' and len(ss) > 1:
                    self.err(ln.no, "no other command may be on the same line as loop start '['")
                    continue
                node = self.parse_cmd(s, ln.no)
                if node is not None:
                    out.append(node)
        return out

    def section(self, ln):
        m = re.fullmatch(r'#([A-Za-z0-9_]+)', ln.text)
        if not m:
            self.err(ln.no, "invalid section header '%s'" % ln.text)
            return None
        nm = m.group(1)
        if nm in self.secs or nm == 'end':
            self.err(ln.no, "section '#%s' defined twice" % nm)
            return None
        self.secs.append(nm)
        return N('section', ln.no, name=nm)

    def parse_if_head(self, s, ln):
        m = re.fullmatch(r'if\s+(\S+)\s+is\s+(\S+)', s)
        if not m:
            self.err(ln.no, "syntax error, expected: if <register> is <value>")
            return None
        r = self.need_reg(m.group(1), ln.no, "first operand of 'if'")
        v = self.operand(m.group(2), ln.no)
        if r is None or v is None:
            return None
        return N('if', ln.no, reg=r[1], val=v, then=[], els=[])

    def parse_if_body(self, node, ln):
        L = self.L
        nx = L[self.p] if self.p < len(L) else None
        if nx is None or nx.text == 'else' or nx.text[0] == '#' or nx.indent <= ln.indent:
            self.err(ln.no, "'if' has no body (indent the code under it)")
        else:
            node.then = self.structure(self.parse_stmts(nx.indent, False))
        nx = L[self.p] if self.p < len(L) else None
        if nx is not None and nx.text == 'else' and nx.indent >= ln.indent:
            eln = nx
            self.p += 1
            nx = L[self.p] if self.p < len(L) else None
            if nx is None or nx.text == 'else' or nx.text[0] == '#' or nx.indent <= eln.indent:
                self.err(eln.no, "'else' has no body (indent the code under it)")
            else:
                node.els = self.structure(self.parse_stmts(nx.indent, False))

    def has_loop(self, n):
        for m in n.then + n.els:
            if m.k == 'loop' or (m.k == 'if' and self.has_loop(m)):
                return True
        return False

    def structure(self, nodes):
        res = []
        cur = res
        op = None
        for n in nodes:
            if n.k == 'lstart':
                if op is not None:
                    self.err(n.no, "loops cannot be nested")
                    continue
                op = N('loop', n.no, body=[])
                res.append(op)
                cur = op.body
            elif n.k == 'lend':
                if op is None:
                    self.err(n.no, "']' without matching '['")
                else:
                    op = None
                    cur = res
            else:
                if op is not None:
                    if n.k == 'section':
                        self.err(n.no, "section header inside a loop")
                        continue
                    if n.k == 'if' and self.has_loop(n):
                        self.err(n.no, "loops cannot be nested")
                        continue
                cur.append(n)
        if op is not None:
            self.err(op.no, "loop '[' is never closed with ']'")
        return res

    def parse_body(self, lines, min_indent):
        if not lines:
            return []
        if lines[0].indent <= min_indent:
            self.err(lines[0].no, "body must be indented deeper than its header")
            return []
        self.L = lines
        self.p = 0
        return self.region(lines[0].indent, False)

    def parse_rest(self, R):
        i = 0
        n = len(R)
        while i < n:
            h = R[i]
            i += 1
            j = i
            while j < n and R[j].indent > h.indent:
                j += 1
            body = R[i:j]
            i = j
            t = h.text
            if t == '@function':
                if not body:
                    self.err(h.no, "'@function' needs 'on input <key>' or 'on port input <port>, <register>' under it")
                    continue
                oi = body[0]
                mp = re.fullmatch(r'on\s+port\s+input\s+(.*)', oi.text)
                if mp:
                    self.parse_port_func(oi, mp.group(1), body[1:])
                    continue
                m = re.fullmatch(r'on\s+input\s+<([^<>]+)>', oi.text)
                if not m:
                    self.err(oi.no, "expected: on input <key>  or  on port input <port>, <register>")
                    continue
                key = m.group(1).strip().lower()
                if key not in KEYS:
                    self.err(oi.no, "unknown key '<%s>'" % m.group(1))
                    continue
                self.funcs.append((KEYS[key], self.parse_body(body[1:], oi.indent)))
            elif t[0] == '!':
                m = re.fullmatch(r'!<([A-Za-z]+)>', t)
                if m and m.group(1) not in BUILTIN:
                    self.cmds.append((m.group(1), self.parse_body(body, h.indent)))
            elif t[0] == '#':
                self.err(h.no, "no sections or '#' lines allowed after '#end'")
            else:
                self.err(h.no, "after '#end' only '@function' and '!<name>' definitions are allowed")

    def port_num(self, tok, no, what):
        o = self.operand(tok, no)
        if o is not None and o[0] == 'num' and not 0 <= o[1] <= 65535:
            self.err(no, "%s %s out of range (0..65535)" % (what, tok))
            return None
        return o

    def parse_port_func(self, oi, rest, body):
        no = oi.no
        m = re.fullmatch(r'(\S+?)\s*,\s*(\S+)', rest.strip())
        if not m:
            self.err(no, 'syntax: on port input <port>, <register>   or   on port input <port>, "number"')
            return
        port = self.port_num(m.group(1), no, 'port number')
        t2 = m.group(2)
        reg = val = None
        q = re.fullmatch(r'"([^"]*)"', t2)
        if q:
            inner = q.group(1).strip()
            if HEX_RE.fullmatch(inner):
                self.err(no, "hex numbers are not allowed (\"%s\"), use a decimal number" % q.group(1))
                return
            if not re.fullmatch(r'[0-9]+', inner):
                self.err(no, "the value in quotes must be a number from 1 to 65535, got '%s'" % q.group(1))
                return
            val = int(inner, 10)
            if val > 65535:
                self.err(no, "port value %d out of range (1..65535)" % val)
                return
            if val == 0:
                self.err(no, "port value 0 means 'no input' and never fires a function, use 1..65535")
                return
        else:
            r = self.need_reg(t2, no, 'second operand')
            if r is None:
                return
            reg = r[1]
        if port is None:
            return
        self.pfuncs.append(N('pfunc', no, port=port, reg=reg, val=val,
                             body=self.parse_body(body, oi.indent)))

    # ---- commands
    def parse_print(self, text, no):
        parts = []
        buf = []

        def flush():
            if buf:
                try:
                    parts.append(('text', ''.join(buf).encode('cp437')))
                except UnicodeEncodeError:
                    self.err(no, "text has a character VGA text mode (CP437) cannot show")
                del buf[:]

        i = 0
        while i < len(text):
            ch = text[i]
            if ch == '$':
                j = text.find('$', i + 1)
                if j == i + 1:
                    buf.append('$')
                    i += 2
                    continue
                if j != -1:
                    inner = text[i + 1:j]
                    if re.fullmatch(r'[A-Z]+', inner):
                        if inner in self.names:
                            flush()
                            parts.append(('var', self.names[inner]))
                            i = j + 1
                            continue
                        self.err(no, "unknown custom name '$%s$' (never set with setname)" % inner)
                        return None
                    if re.fullmatch(r'[A-Za-z]+', inner):
                        self.err(no, "custom names are CAPITAL letters only: '$%s$'" % inner)
                        return None
            buf.append(ch)
            i += 1
        flush()
        return N('print', no, parts=parts)

    def parse_cmd(self, s, no):
        if s == '[':
            return N('lstart', no)
        if s == ']':
            return N('lend', no)
        parts = s.split(None, 1)
        cmd = parts[0]
        rest = parts[1].strip() if len(parts) > 1 else ''
        if cmd == 'else':
            self.err(no, "'else' must be alone on its own line")
            return None
        if cmd in ('exit', 'return', 'nop', 'halt', 'resume'):
            if rest:
                self.err(no, "'%s' takes no operands" % cmd)
                return None
            return N(cmd, no)
        if cmd == 'print':
            m = re.fullmatch(r'"([^"]*)"', rest)
            if not m:
                self.err(no, 'print needs text in double quotes, e.g. print "hi $NAME$"')
                return None
            return self.parse_print(m.group(1), no)
        if cmd in ('jump', 'skip'):
            m = re.fullmatch(r'#([A-Za-z0-9_]+)', rest)
            if not m:
                self.err(no, "syntax: %s #section" % cmd)
                return None
            if cmd == 'skip' and m.group(1) == 'end':
                self.err(no, "cannot skip '#end'")
                return None
            self.refs.append((cmd, m.group(1), no))
            return N(cmd, no, name=m.group(1))
        if cmd == 'setname':
            return N('setname', no)
        if cmd in ('add', 'sub', 'mul'):
            a = self.args(rest, no, cmd)
            if a is None:
                return None
            if len(a) < 2:
                self.err(no, "'%s' needs a register and at least one more operand" % cmd)
                return None
            dst = self.need_reg(a[0], no)
            ops = [self.operand(t, no) for t in a[1:]]
            if dst is None or any(o is None for o in ops):
                return None
            return N(cmd, no, dst=dst[1], ops=ops)
        if cmd == 'div':
            a = self.args(rest, no, cmd)
            if a is None:
                return None
            if len(a) != 2:
                self.err(no, "'div' takes exactly 2 operands")
                return None
            dst = self.need_reg(a[0], no)
            op = self.operand(a[1], no)
            if dst is None or op is None:
                return None
            return N('div', no, dst=dst[1], op=op)
        if cmd == 'move':
            a = self.args(rest, no, cmd)
            if a is None:
                return None
            if len(a) != 2:
                self.err(no, "'move' takes exactly 2 operands")
                return None
            x = self.need_reg(a[0], no)
            y = self.need_reg(a[1], no, 'second operand')
            if x is None or y is None:
                return None
            return N('move', no, src=x[1], dst=y[1])
        if cmd == 'copy':
            a = self.args(rest, no, cmd)
            if a is None:
                return None
            if len(a) < 2:
                self.err(no, "'copy' needs a source and at least one destination register")
                return None
            src = self.operand(a[0], no)
            ds = [self.need_reg(t, no, 'destination') for t in a[1:]]
            if src is None or any(d is None for d in ds):
                return None
            return N('copy', no, src=src, dsts=[d[1] for d in ds])
        if cmd in ('stackadd', 'stack2add'):
            a = self.args(rest, no, cmd)
            if a is None:
                return None
            if len(a) != 1:
                self.err(no, "'%s' takes exactly 1 operand" % cmd)
                return None
            op = self.operand(a[0], no)
            if op is None:
                return None
            return N('sadd', no, st=2 if cmd == 'stack2add' else 1, op=op)
        if cmd in ('stacktake', 'stack2take'):
            a = self.args(rest, no, cmd)
            if a is None:
                return None
            if len(a) != 1:
                self.err(no, "'%s' takes exactly 1 operand" % cmd)
                return None
            r = self.need_reg(a[0], no, 'operand')
            if r is None:
                return None
            return N('stake', no, st=2 if cmd == 'stack2take' else 1, reg=r[1])
        if cmd == 'random':
            a = self.args(rest, no, cmd)
            if a is None:
                return None
            if len(a) != 1:
                self.err(no, "'random' takes exactly 1 operand")
                return None
            r = self.need_reg(a[0], no, 'operand')
            if r is None:
                return None
            return N('random', no, reg=r[1])
        if cmd == 'output':
            a = self.args(rest, no, cmd)
            if a is None:
                return None
            if len(a) != 2:
                self.err(no, "'output' takes exactly 2 operands (port, data)")
                return None
            p = self.port_num(a[0], no, 'port number')
            d = self.operand(a[1], no)
            if d is not None and d[0] == 'num' and not 0 <= d[1] <= 65535:
                self.err(no, "output data %s out of range (0..65535)" % a[1])
                return None
            if p is None or d is None:
                return None
            return N('output', no, port=p, data=d)
        if cmd == 'compare':
            a = self.args(rest, no, cmd)
            if a is None:
                return None
            if len(a) != 2:
                self.err(no, "'compare' takes exactly 2 operands")
                return None
            x = self.operand(a[0], no)
            y = self.operand(a[1], no)
            if x is None or y is None:
                return None
            return N('compare', no, x=x, y=y)
        if cmd in self.custom:
            if rest:
                self.err(no, "custom command '%s' takes no operands" % cmd)
                return None
            return N('call', no, name=cmd)
        self.err(no, "unknown command '%s'" % cmd)
        return None


# ---------------------------------------------------------------- back end
class Gen:
    def __init__(self, c, o):
        self.c = c
        self.o = o
        self.a = Asm()
        self.strs = {}
        b = Bss()
        self.bss = b
        b.alloc('regs', 16)
        b.alloc('mem', 4096 * 4)
        b.alloc('st1', 20)
        b.alloc('st2', 20)
        for nm in ('curs', 'inh', 'halted', 'rng', 'savesp', 'kext', 'kqh', 'kqt', 'rsp', 'rdepth'):
            b.alloc(nm, 4)
        b.alloc('kq', 64)
        b.alloc('rstk', 256)
        if c.pfuncs:
            b.alloc('pq', 64)
            b.alloc('pqh', 4)
            b.alloc('pqt', 4)
            b.alloc('plast', 4 * len(c.pfuncs))
            b.alloc('pport', 4 * len(c.pfuncs))
            b.alloc('pseq', 4)               # poll counter: events found in one poll are simultaneous
            b.alloc('pbs', 4)                # tail of the port queue when the current scan began
            b.alloc('kqs', 64)               # poll number each queued key was found in
            b.alloc('pqs', 64)               # same for queued port events
        b.alloc('skip', 4 * len(c.secs))
        b.alloc('stack', 8192)
        self.stack_top = b.o['stack'] + 8192
        self.after = {}
        for i, nm in enumerate(c.secs):
            if i + 1 < len(c.secs):
                self.after[nm] = 'H_' + c.secs[i + 1]
            else:
                self.after[nm] = 'END'

    def V(self, name, add=0):
        return ('bss', self.bss.o[name] + add)

    def X(self, name, add, idx):
        return ('bssx', self.bss.o[name] + add, idx, 4)

    def skipoff(self, name):
        return self.bss.o['skip'] + 4 * self.c.secs.index(name)

    def load(self, r, op):
        if op[0] == 'reg':
            self.a.mov_rm(r, ('bss', op[1]))
        else:
            self.a.mov_ri(r, op[1])

    def build(self):
        self.emit()
        a = self.a
        bss0 = (len(a.b) + 15) & ~15
        a.resolve(bss0)
        img = bytes(a.b) + bytes(bss0 - len(a.b))
        return img, self.bss.size

    def emit(self):
        a = self.a
        self.prologue()
        self.gen(self.c.main, 'main')
        a.label('END')
        w = a.new()
        a.label(w)
        a.call('poll')
        a.raw(0xF3, 0x90)
        a.jmp(w)
        for name, body in self.c.cmds:
            a.label('C_' + name)
            self.gen(body, 'sub')
            a.raw(0xC3)
        for i, (key, body) in enumerate(self.c.funcs):
            a.label('F_%d' % i)
            self.gen(body, 'sub')
            a.raw(0xC3)
        # one ftab entry per key. several functions on the same key trigger at the same
        # moment, so they go through a small stub that runs them in a random order
        groups = {}
        for i, (key, body) in enumerate(self.c.funcs):
            groups.setdefault(key, []).append(i)
        self.ftab = []
        for key, g in groups.items():
            if len(g) == 1:
                self.ftab.append((key, 'F_%d' % g[0]))
            else:
                lab = 'FG_%d' % key
                self.gen_group(lab, g)
                self.ftab.append((key, lab))
        for i, pf in enumerate(self.c.pfuncs):
            a.label('PF_%d' % i)             # eax = value read from the port
            if pf.reg is not None:
                a.mov_mr(('bss', pf.reg), EAX)
            self.gen(pf.body, 'sub')
            a.raw(0xC3)
        self.runtime()
        while len(a.b) % 4:
            a.raw(0)
        a.label('ftab')
        for key, lab in self.ftab:
            a.dd(key)
            a.fx('lbl', lab)
        a.label('ptab')
        for i in range(len(self.c.pfuncs)):
            a.fx('lbl', 'PF_%d' % i)
        for data, lab in self.strs.items():
            a.label(lab)
            a.b.extend(data)

    def gen_group(self, lab, g):
        # g = indexes of the functions that share one key. random one first, the others follow
        a = self.a
        m = len(g)
        a.label(lab)
        a.call('random')
        a.xor_rr(EDX, EDX)
        a.mov_ri(ECX, m)
        a.div(ECX)                           # edx = random 0..m-1
        for r in range(m):
            nx = a.new()
            if r < m - 1:
                a.cmp_ri(EDX, r)
                a.jcc(CC_NE, nx)
            for t in range(m):
                a.call('F_%d' % g[(r + t) % m])
            a.raw(0xC3)
            if r < m - 1:
                a.label(nx)

    def prologue(self):
        a = self.a
        V = self.V
        a.raw(0x60, 0xFA, 0xFC)              # pushad, cli, cld
        a.raw(0xE8, 0, 0, 0, 0)              # call next
        nxt = len(a.b)
        a.raw(0x5D)                          # pop ebp
        a.sub_ri(EBP, nxt)                   # ebp = image base
        a.lea(EDI, ('bss', 0))
        a.mov_ri(ECX, self.bss.size // 4)
        a.xor_rr(EAX, EAX)
        a.raw(0xF3, 0xAB)                    # rep stosd (zero bss)
        a.mov_mr(V('savesp'), ESP)
        a.lea(ESP, ('bss', self.stack_top))
        fl = a.new()
        fd = a.new()
        a.mov_ri(ECX, 16)
        a.label(fl)
        a.raw(0xE4, 0x64, 0xA8, 0x01)        # in al,0x64 ; test al,1
        a.jcc(CC_E, fd)
        a.raw(0xE4, 0x60)                    # in al,0x60 (flush)
        a.dec(ECX)
        a.jcc(CC_NE, fl)
        a.label(fd)
        if not self.o.no_clear:
            a.mov_ri(EDI, 0xB8000)
            a.mov_ri(ECX, 1000)
            a.mov_ri(EAX, 0x07200720)
            a.raw(0xF3, 0xAB)
            a.call('hwcur')

    def gen(self, nodes, ctx):
        for n in nodes:
            getattr(self, 'g_' + n.k)(n, ctx)
            # continuous polling: check keys + ports after every statement
            # (queues while a handler is running, dispatches when free)
            if n.k not in ('section', 'setname'):
                self.a.call('poll')

    # ---- statements
    def g_section(self, n, ctx):
        a = self.a
        a.label('H_' + n.name)
        if n.name in self.c.skipped:
            a.cmp_m8i(('bss', self.skipoff(n.name)), 0)
            a.jcc(CC_NE, self.after[n.name])
        a.label('S_' + n.name)

    def g_setname(self, n, ctx):
        pass

    def g_nop(self, n, ctx):
        self.a.raw(0x90)

    def arith(self, n, op):
        a = self.a
        a.mov_rm(EAX, ('bss', n.dst))
        for o in n.ops:
            if o[0] == 'reg':
                m = ('bss', o[1])
                if op == 'add':
                    a.add_rm(EAX, m)
                elif op == 'sub':
                    a.sub_rm(EAX, m)
                else:
                    a.imul_rm(EAX, m)
            else:
                if op == 'add':
                    a.add_ri(EAX, o[1])
                elif op == 'sub':
                    a.sub_ri(EAX, o[1])
                else:
                    a.imul_rri(EAX, EAX, o[1])
        a.mov_mr(('bss', n.dst), EAX)

    def g_add(self, n, ctx):
        self.arith(n, 'add')

    def g_sub(self, n, ctx):
        self.arith(n, 'sub')

    def g_mul(self, n, ctx):
        self.arith(n, 'mul')

    def g_div(self, n, ctx):
        a = self.a
        z = a.new()
        ng = a.new()
        st = a.new()
        self.load(EAX, ('reg', n.dst))
        self.load(ECX, n.op)
        a.test_rr(ECX, ECX)
        a.jcc(CC_E, z)
        a.cmp_ri(ECX, 0xFFFFFFFF)
        a.jcc(CC_E, ng)
        a.raw(0x99)                          # cdq
        a.idiv(ECX)
        a.jmp(st)
        a.label(z)
        a.xor_rr(EAX, EAX)
        a.xor_rr(EDX, EDX)
        a.jmp(st)
        a.label(ng)
        a.neg(EAX)
        a.xor_rr(EDX, EDX)
        a.label(st)
        a.mov_mr(('bss', 12), EDX)
        a.mov_mr(('bss', n.dst), EAX)

    def g_move(self, n, ctx):
        a = self.a
        a.mov_rm(EAX, ('bss', n.src))
        a.mov_mi(('bss', n.src), 0)
        a.mov_mr(('bss', n.dst), EAX)

    def g_copy(self, n, ctx):
        self.load(EAX, n.src)
        for d in n.dsts:
            self.a.mov_mr(('bss', d), EAX)

    def g_jump(self, n, ctx):
        a = self.a
        tgt = 'END' if n.name == 'end' else 'S_' + n.name
        if ctx == 'main':
            r = a.new('R')
            a.call('poll')
            a.mov_rl(ECX, r)
            a.call('rpush')
            a.jmp(tgt)
            a.label(r)
        else:
            a.lea(ESP, ('bss', self.stack_top))
            a.mov_mi(self.V('inh'), 0)
            a.jmp(tgt)

    def g_return(self, n, ctx):
        a = self.a
        if ctx == 'main':
            sk = a.new()
            a.call('poll')
            a.call('rpop')
            a.cmp_ri(ECX, 0xFFFFFFFF)
            a.jcc(CC_E, sk)
            a.add_rr(ECX, EBP)
            a.jmp_r(ECX)
            a.label(sk)
        else:
            a.raw(0xC3)

    def g_skip(self, n, ctx):
        self.a.mov_m8i(('bss', self.skipoff(n.name)), 1)

    def g_call(self, n, ctx):
        self.a.call('C_' + n.name)

    def g_halt(self, n, ctx):
        a = self.a
        h = a.new()
        a.mov_mi(self.V('halted'), 1)
        a.label(h)
        a.call('poll_halt')
        a.raw(0xF3, 0x90)
        a.cmp_mi(self.V('halted'), 0)
        a.jcc(CC_NE, h)

    def g_resume(self, n, ctx):
        self.a.mov_mi(self.V('halted'), 0)

    def g_exit(self, n, ctx):
        a = self.a
        m = self.o.exitmode
        if m == 'ret':
            a.mov_rm(ESP, self.V('savesp'))
            a.raw(0x61, 0xC3)
            return
        if m == 'reboot':
            w = a.new()
            a.label(w)
            a.raw(0xE4, 0x64, 0xA8, 0x02)
            a.jcc(CC_NE, w)
            a.raw(0xB0, 0xFE, 0xE6, 0x64)
        h = a.new()
        a.label(h)
        a.raw(0xFA, 0xF4)
        a.jmp(h)

    def g_print(self, n, ctx):
        a = self.a
        for kind, v in n.parts:
            if kind == 'text':
                lab = self.strs.get(v)
                if lab is None:
                    lab = 'STR%d' % len(self.strs)
                    self.strs[v] = lab
                a.lea(ESI, ('lbl', lab))
                a.mov_ri(EBX, len(v))
                a.call('print_str')
            else:
                a.mov_rm(EAX, ('bss', v))
                a.call('print_dec')
        a.call('newline')

    def g_if(self, n, ctx):
        a = self.a
        lelse = a.new()
        lend = a.new()
        a.mov_rm(EAX, ('bss', n.reg))
        if n.val[0] == 'reg':
            a.cmp_rm(EAX, ('bss', n.val[1]))
        else:
            a.cmp_ri(EAX, n.val[1])
        a.jcc(CC_NE, lelse)
        self.gen(n.then, ctx)
        if n.els:
            a.jmp(lend)
            a.label(lelse)
            self.gen(n.els, ctx)
            a.label(lend)
        else:
            a.label(lelse)

    def g_loop(self, n, ctx):
        a = self.a
        top = a.new()
        end = a.new()
        neg = a.new()
        store = a.new()
        c = ('bss', 8)
        a.cmp_mi(c, 0)
        a.jcc(CC_E, end)
        a.label(top)
        self.gen(n.body, ctx)
        a.call('poll')
        a.mov_rm(EAX, c)
        a.test_rr(EAX, EAX)
        a.jcc(CC_E, end)
        a.jcc(CC_S, neg)
        a.dec(EAX)
        a.jmp(store)
        a.label(neg)
        a.inc(EAX)
        a.label(store)
        a.mov_mr(c, EAX)
        a.test_rr(EAX, EAX)
        a.jcc(CC_NE, top)
        a.label(end)

    def g_sadd(self, n, ctx):
        a = self.a
        st = 'st%d' % n.st
        sk = a.new()
        self.load(EAX, n.op)
        a.mov_rm(ECX, self.V(st))
        a.cmp_ri(ECX, 4)
        a.jcc(CC_AE, sk)
        a.mov_mr(self.X(st, 4, ECX), EAX)
        a.inc(ECX)
        a.mov_mr(self.V(st), ECX)
        if n.op[0] == 'reg':
            a.mov_mi(('bss', n.op[1]), 0)
        a.label(sk)

    def g_stake(self, n, ctx):
        a = self.a
        st = 'st%d' % n.st
        store = a.new()
        a.xor_rr(EAX, EAX)
        a.mov_rm(ECX, self.V(st))
        a.test_rr(ECX, ECX)
        a.jcc(CC_E, store)
        a.dec(ECX)
        a.mov_rm(EAX, self.X(st, 4, ECX))
        a.mov_mr(self.V(st), ECX)
        a.label(store)
        a.mov_mr(('bss', n.reg), EAX)

    def g_compare(self, n, ctx):
        a = self.a
        st = a.new()
        self.load(EAX, n.x)
        if n.y[0] == 'reg':
            a.cmp_rm(EAX, ('bss', n.y[1]))
        else:
            a.cmp_ri(EAX, n.y[1])
        a.mov_ri(EDX, 0)
        a.jcc(CC_E, st)
        a.mov_ri(EDX, 1)
        a.jcc(CC_G, st)
        a.mov_ri(EDX, 0xFFFFFFFF)
        a.label(st)
        a.mov_mr(('bss', 12), EDX)

    def g_output(self, n, ctx):
        a = self.a
        self.load(EAX, n.data)
        self.load(EDX, n.port)
        a.raw(0x66, 0xEF)                    # out dx,ax

    def g_random(self, n, ctx):
        self.a.call('random')
        self.a.mov_mr(('bss', n.reg), EAX)

    # ---- runtime routines
    def runtime(self):
        self.rt_poll()
        self.rt_dispatch()
        if self.c.pfuncs:
            self.rt_ports()
        self.rt_screen()
        self.rt_misc()

    def rt_poll(self):
        a = self.a
        V = self.V
        nxt, disp, notE0, rel, done, dloop = [a.new() for _ in range(6)]
        ports = bool(self.c.pfuncs)
        a.label('poll')
        a.raw(0x60)                          # pushad
        if ports:
            a.mov_rm(EAX, V('pseq'))         # every poll is one tick of time
            a.inc(EAX)
            a.mov_mr(V('pseq'), EAX)
        a.label(nxt)
        a.raw(0xE4, 0x64)                    # in al,0x64
        a.raw(0x3C, 0xFF)                    # cmp al,0xFF (no controller)
        a.jcc(CC_E, disp)
        a.raw(0xA8, 0x01)                    # test al,1
        a.jcc(CC_E, disp)
        a.movzx8(EDX, 0)                     # edx = status
        a.raw(0xE4, 0x60)                    # in al,0x60
        a.raw(0xF6, 0xC2, 0x20)              # test dl,0x20 (mouse byte)
        a.jcc(CC_NE, nxt)
        a.movzx8(EAX, 0)
        a.cmp_ri(EAX, 0xE0)
        a.jcc(CC_NE, notE0)
        a.mov_mi(V('kext'), 0x100)
        a.jmp(nxt)
        a.label(notE0)
        a.cmp_ri(EAX, 0xE1)
        a.jcc(CC_E, nxt)
        a.test_ri(EAX, 0x80)
        a.jcc(CC_NE, rel)
        a.or_rm(EAX, V('kext'))
        a.mov_mi(V('kext'), 0)
        # queue the key. head/tail count 0..31, slot = index & 15, full when 16 are queued
        a.mov_rm(ECX, V('kqt'))
        a.mov_rr(EDX, ECX)
        a.sub_rm(EDX, V('kqh'))
        a.and_ri(EDX, 31)
        a.cmp_ri(EDX, 16)
        a.jcc(CC_AE, nxt)                    # 16 already waiting: drop this key
        a.mov_rr(EDX, ECX)
        a.inc(EDX)
        a.and_ri(EDX, 31)
        a.and_ri(ECX, 15)
        a.mov_mr(self.X('kq', 0, ECX), EAX)
        if ports:
            a.mov_rm(EBX, V('pseq'))
            a.mov_mr(self.X('kqs', 0, ECX), EBX)
        a.mov_mr(V('kqt'), EDX)
        a.jmp(nxt)
        a.label(rel)
        a.mov_mi(V('kext'), 0)
        a.jmp(nxt)
        a.label(disp)
        if ports:
            a.call('pscan')
        a.cmp_mi(V('inh'), 0)
        a.jcc(CC_NE, done)
        a.label(dloop)
        if not ports:
            a.mov_rm(ESI, V('kqh'))
            a.cmp_rm(ESI, V('kqt'))
            a.jcc(CC_E, done)
            a.mov_rr(ECX, ESI)
            a.and_ri(ECX, 15)
            a.mov_rm(EAX, self.X('kq', 0, ECX))
            a.inc(ESI)
            a.and_ri(ESI, 31)
            a.mov_mr(V('kqh'), ESI)
            a.mov_mi(V('inh'), 1)
            a.call('dispatch')
            a.mov_mi(V('inh'), 0)
            a.jmp(dloop)
        else:
            nokey, dokey, doport, tie = [a.new() for _ in range(4)]
            a.mov_rm(ESI, V('kqh'))          # esi = key queue head
            a.cmp_rm(ESI, V('kqt'))
            a.jcc(CC_E, nokey)
            a.mov_rm(EDI, V('pqh'))          # edi = port queue head
            a.cmp_rm(EDI, V('pqt'))
            a.jcc(CC_E, dokey)
            # both queues have something: the older poll goes first, same poll = random
            a.mov_rr(EBX, ESI)
            a.and_ri(EBX, 15)
            a.mov_rm(EAX, self.X('kqs', 0, EBX))
            a.mov_rr(ECX, EDI)
            a.and_ri(ECX, 15)
            a.sub_rm(EAX, self.X('pqs', 0, ECX))
            a.jcc(CC_E, tie)
            a.jcc(CC_S, dokey)               # key stamp is older
            a.jmp(doport)
            a.label(tie)
            a.call('random')
            a.test_ri(EAX, 0x10000)
            a.jcc(CC_E, dokey)
            a.jmp(doport)
            a.label(nokey)
            a.mov_rm(EDI, V('pqh'))
            a.cmp_rm(EDI, V('pqt'))
            a.jcc(CC_E, done)
            a.label(doport)
            a.mov_rr(ECX, EDI)
            a.and_ri(ECX, 15)
            a.mov_rm(EAX, self.X('pq', 0, ECX))
            a.inc(EDI)
            a.and_ri(EDI, 31)
            a.mov_mr(V('pqh'), EDI)
            a.mov_mi(V('inh'), 1)
            a.call('pdispatch')
            a.mov_mi(V('inh'), 0)
            a.jmp(dloop)
            a.label(dokey)
            a.mov_rr(ECX, ESI)
            a.and_ri(ECX, 15)
            a.mov_rm(EAX, self.X('kq', 0, ECX))
            a.inc(ESI)
            a.and_ri(ESI, 31)
            a.mov_mr(V('kqh'), ESI)
            a.mov_mi(V('inh'), 1)
            a.call('dispatch')
            a.mov_mi(V('inh'), 0)
            a.jmp(dloop)
        a.label(done)
        a.raw(0x61, 0xC3)                    # popad, ret

        a.label('poll_halt')
        a.push_m(V('inh'))
        a.mov_mi(V('inh'), 0)
        a.call('poll')
        a.pop_m(V('inh'))
        a.raw(0xC3)

    def rt_ports(self):
        a = self.a
        V = self.V
        n = len(self.c.pfuncs)
        # pscan: read every port function's port, queue (index<<16 | value) when the port
        # gets a NEW NON-ZERO value. going back to 0 only updates the remembered value.
        # called from poll (after pushad), clobbers everything.
        a.label('pscan')
        a.mov_rm(EAX, V('pqt'))
        a.mov_mr(V('pbs'), EAX)                         # remember where this scan's events start
        for i, pf in enumerate(self.c.pfuncs):
            nx, up = a.new(), a.new()
            if pf.port[0] == 'num':
                a.mov_ri(EDX, pf.port[1])
            else:
                same = a.new()
                a.mov_rm(EDX, ('bss', pf.port[1]))
                a.and_ri(EDX, 0xFFFF)
                a.cmp_rm(EDX, V('pport', 4 * i))
                a.jcc(CC_E, same)
                a.mov_mr(V('pport', 4 * i), EDX)        # port changed: new port starts idle (0)
                a.mov_mi(V('plast', 4 * i), 0)
                a.label(same)
            a.raw(0x66, 0xED)                           # in ax,dx
            a.movzx16(EAX, EAX)
            a.cmp_rm(EAX, V('plast', 4 * i))
            a.jcc(CC_E, nx)
            a.test_rr(EAX, EAX)
            a.jcc(CC_E, up)                             # back to 0 = no input: remember it, nothing fires
            if pf.val is not None:
                a.cmp_ri(EAX, pf.val)
                a.jcc(CC_NE, up)                        # not the awaited value: just remember it
            a.mov_rm(ECX, V('pqt'))
            a.mov_rr(EDX, ECX)
            a.sub_rm(EDX, V('pqh'))
            a.and_ri(EDX, 31)
            a.cmp_ri(EDX, 16)
            a.jcc(CC_AE, nx)                            # 16 waiting: keep old value, retry next poll
            a.mov_rr(EBX, EAX)
            a.add_ri(EBX, i << 16)
            a.mov_rr(EDX, ECX)
            a.inc(EDX)
            a.and_ri(EDX, 31)
            a.and_ri(ECX, 15)
            a.mov_mr(self.X('pq', 0, ECX), EBX)
            a.mov_rm(EBX, V('pseq'))
            a.mov_mr(self.X('pqs', 0, ECX), EBX)
            a.mov_mr(V('pqt'), EDX)
            a.label(up)
            a.mov_mr(V('plast', 4 * i), EAX)
            a.label(nx)
        if n >= 2:
            # events found in this scan are simultaneous: shuffle them (Fisher-Yates)
            sh, shd = a.new(), a.new()
            a.mov_rm(ESI, V('pqt'))
            a.sub_rm(ESI, V('pbs'))
            a.and_ri(ESI, 31)                           # esi = k new events
            a.cmp_ri(ESI, 2)
            a.jcc(CC_B, shd)
            a.label(sh)
            a.dec(ESI)                                  # j = k-1 .. 1
            a.jcc(CC_E, shd)
            a.call('random')
            a.xor_rr(EDX, EDX)
            a.mov_rr(ECX, ESI)
            a.inc(ECX)
            a.div(ECX)                                  # edx = random 0..j
            a.mov_rm(EBX, V('pbs'))
            a.mov_rr(ECX, EBX)
            a.add_rr(ECX, ESI)
            a.and_ri(ECX, 15)                           # slot of entry j
            a.add_rr(EBX, EDX)
            a.and_ri(EBX, 15)                           # slot of entry r
            a.mov_rm(EAX, self.X('pq', 0, ECX))
            a.mov_rm(EDX, self.X('pq', 0, EBX))
            a.mov_mr(self.X('pq', 0, ECX), EDX)
            a.mov_mr(self.X('pq', 0, EBX), EAX)
            a.jmp(sh)
            a.label(shd)
        a.raw(0xC3)
        # pdispatch: eax = index<<16 | value -> run that port function with eax = value
        a.label('pdispatch')
        a.mov_rr(ECX, EAX)
        a.shr(ECX, 16)
        a.movzx16(EAX, EAX)
        a.mov_rm(EDX, ('lblx', 'ptab', ECX, 4))
        a.add_rr(EDX, EBP)
        a.jmp_r(EDX)

    def rt_dispatch(self):
        a = self.a
        dl, de, ds = a.new(), a.new(), a.new()
        a.label('dispatch')                  # eax = key code
        a.lea(ESI, ('lbl', 'ftab'))
        a.mov_ri(ECX, len(self.ftab))
        a.label(dl)
        a.test_rr(ECX, ECX)
        a.jcc(CC_E, de)
        a.cmp_rm(EAX, ('r', ESI))
        a.jcc(CC_NE, ds)
        a.push(EAX)
        a.push(ECX)
        a.push(ESI)
        a.mov_rm(EDX, ('rd', ESI, 4))
        a.add_rr(EDX, EBP)
        a.call_r(EDX)
        a.pop(ESI)
        a.pop(ECX)
        a.pop(EAX)
        a.label(ds)
        a.add_ri(ESI, 8)
        a.dec(ECX)
        a.jmp(dl)
        a.label(de)
        a.raw(0xC3)

    def rt_screen(self):
        a = self.a
        V = self.V
        # putc: al = char
        ok = a.new()
        a.label('putc')
        a.mov_rm(ECX, V('curs'))
        a.cmp_ri(ECX, 2000)
        a.jcc(CC_B, ok)
        a.call('scroll')
        a.mov_rm(ECX, V('curs'))
        a.label(ok)
        a.mov_rr(EDI, ECX)
        a.shl(EDI, 1)
        a.add_ri(EDI, 0xB8000)
        a.raw(0xB4, 0x07)                    # mov ah,7
        a.raw(0x66, 0xAB)                    # stosw
        a.inc(ECX)
        a.mov_mr(V('curs'), ECX)
        a.raw(0xC3)
        # scroll one line up (preserves all regs)
        a.label('scroll')
        a.raw(0x60)
        a.mov_ri(EDI, 0xB8000)
        a.mov_ri(ESI, 0xB8000 + 160)
        a.mov_ri(ECX, 960)
        a.raw(0xF3, 0xA5)                    # rep movsd
        a.mov_ri(EDI, 0xB8000 + 3840)
        a.mov_ri(EAX, 0x07200720)
        a.mov_ri(ECX, 40)
        a.raw(0xF3, 0xAB)                    # rep stosd
        a.mov_mi(V('curs'), 1920)
        a.raw(0x61, 0xC3)
        # print_str: esi = ptr, ebx = len
        pl, pd = a.new(), a.new()
        a.label('print_str')
        a.label(pl)
        a.test_rr(EBX, EBX)
        a.jcc(CC_E, pd)
        a.raw(0x8A, 0x06)                    # mov al,[esi]
        a.inc(ESI)
        a.dec(EBX)
        a.call('putc')
        a.jmp(pl)
        a.label(pd)
        a.raw(0xC3)
        # print_dec: eax signed
        pos, dl, ol = a.new(), a.new(), a.new()
        a.label('print_dec')
        a.test_rr(EAX, EAX)
        a.jcc(CC_NS, pos)
        a.push(EAX)
        a.raw(0xB0, 0x2D)                    # mov al,'-'
        a.call('putc')
        a.pop(EAX)
        a.neg(EAX)
        a.label(pos)
        a.mov_ri(ECX, 10)
        a.xor_rr(EBX, EBX)
        a.label(dl)
        a.xor_rr(EDX, EDX)
        a.div(ECX)
        a.add_ri(EDX, 0x30)
        a.push(EDX)
        a.inc(EBX)
        a.test_rr(EAX, EAX)
        a.jcc(CC_NE, dl)
        a.label(ol)
        a.pop(EAX)
        a.call('putc')
        a.dec(EBX)
        a.jcc(CC_NE, ol)
        a.raw(0xC3)
        # newline
        nk = a.new()
        a.label('newline')
        a.mov_rm(EAX, V('curs'))
        a.mov_ri(ECX, 80)
        a.xor_rr(EDX, EDX)
        a.div(ECX)
        a.inc(EAX)
        a.imul_rri(EAX, EAX, 80)
        a.mov_mr(V('curs'), EAX)
        a.cmp_ri(EAX, 2000)
        a.jcc(CC_B, nk)
        a.call('scroll')
        a.label(nk)
        a.call('hwcur')
        a.raw(0xC3)
        # hardware cursor
        a.label('hwcur')
        a.mov_rm(ECX, V('curs'))
        a.mov_ri(EDX, 0x3D4)
        a.raw(0xB0, 0x0F, 0xEE)              # mov al,0x0F ; out dx,al
        a.inc(EDX)
        a.raw(0x88, 0xC8, 0xEE)              # mov al,cl ; out dx,al
        a.dec(EDX)
        a.raw(0xB0, 0x0E, 0xEE)              # mov al,0x0E ; out dx,al
        a.inc(EDX)
        a.raw(0x88, 0xE8, 0xEE)              # mov al,ch ; out dx,al
        a.raw(0xC3)

    def rt_misc(self):
        a = self.a
        V = self.V
        # rpush: ecx = value
        full = a.new()
        a.label('rpush')
        a.mov_rm(EAX, V('rsp'))
        a.mov_mr(self.X('rstk', 0, EAX), ECX)
        a.inc(EAX)
        a.and_ri(EAX, 63)
        a.mov_mr(V('rsp'), EAX)
        a.mov_rm(EAX, V('rdepth'))
        a.cmp_ri(EAX, 64)
        a.jcc(CC_AE, full)
        a.inc(EAX)
        a.mov_mr(V('rdepth'), EAX)
        a.label(full)
        a.raw(0xC3)
        # rpop: ecx = value or -1
        have = a.new()
        a.label('rpop')
        a.mov_rm(ECX, V('rdepth'))
        a.test_rr(ECX, ECX)
        a.jcc(CC_NE, have)
        a.mov_ri(ECX, 0xFFFFFFFF)
        a.raw(0xC3)
        a.label(have)
        a.dec(ECX)
        a.mov_mr(V('rdepth'), ECX)
        a.mov_rm(EAX, V('rsp'))
        a.dec(EAX)
        a.and_ri(EAX, 63)
        a.mov_mr(V('rsp'), EAX)
        a.mov_rm(ECX, self.X('rstk', 0, EAX))
        a.raw(0xC3)
        # random -> eax
        nz, ok = a.new(), a.new()
        a.label('random')
        a.raw(0x0F, 0x31)                    # rdtsc
        a.xor_rm(EAX, V('rng'))
        a.test_rr(EAX, EAX)
        a.jcc(CC_NE, nz)
        a.mov_ri(EAX, 0x6D2B79F5)
        a.label(nz)
        a.mov_rr(EDX, EAX)
        a.shl(EDX, 13)
        a.xor_rr(EAX, EDX)
        a.mov_rr(EDX, EAX)
        a.shr(EDX, 17)
        a.xor_rr(EAX, EDX)
        a.mov_rr(EDX, EAX)
        a.shl(EDX, 5)
        a.xor_rr(EAX, EDX)
        a.mov_mr(V('rng'), EAX)
        a.cmp_ri(EAX, 0x80000000)
        a.jcc(CC_NE, ok)
        a.inc(EAX)
        a.label(ok)
        a.raw(0xC3)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(prog='magicc', description='Magic (.mmx) -> .cmc compiler')
    ap.add_argument('src')
    ap.add_argument('-o', dest='out')
    ap.add_argument('--exit', dest='exitmode', choices=('halt', 'ret', 'reboot'), default='halt',
                    help="what 'exit' does: cli/hlt loop, return to loader (popad+ret), or reset via KBC")
    ap.add_argument('--no-clear', action='store_true', help='do not clear the screen at start')
    ap.add_argument('--pad', action='store_true', help='append BSS zeros to the output file')
    o = ap.parse_args()
    try:
        with open(o.src, 'r', encoding='utf-8-sig') as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print('magicc: cannot read %s: %s' % (o.src, e), file=sys.stderr)
        return 1
    c = Compiler(text)
    c.compile()
    if c.errs:
        for no, msg in sorted(set(c.errs)):
            print('%s:%d: error: %s' % (o.src, no, msg), file=sys.stderr)
            if 1 <= no <= len(c.src):
                print('    %5d | %s' % (no, c.src[no - 1].rstrip()), file=sys.stderr)
        n = len(set(c.errs))
        print('%d error%s, nothing written' % (n, '' if n == 1 else 's'), file=sys.stderr)
        return 1
    g = Gen(c, o)
    try:
        img, bss = g.build()
    except (KeyError, AssertionError) as e:
        print('magicc: internal error: %r' % (e,), file=sys.stderr)
        return 2
    if o.pad:
        img += bytes(bss)
    out = o.out or (os.path.splitext(o.src)[0] + '.cmc')
    with open(out, 'wb') as f:
        f.write(img)
    print('%s: %d bytes, needs %d bytes BSS after image%s, entry +0, flat32 position independent'
          % (out, len(img), bss, ' (padded in file)' if o.pad else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
