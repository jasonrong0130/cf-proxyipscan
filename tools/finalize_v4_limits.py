from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_exact(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"marker not found in {path}: {old!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Frontend: keep conservative defaults, but let faster machines raise concurrency.
replace_exact(
    "combined_refactor/index.html",
    '<div class="formrow"><label>测试并发</label><input class="input" id="threads" type="number" value="8" min="1" max="16"></div>',
    '<div class="formrow"><label>测试并发</label><input class="input" id="threads" type="number" value="8" min="1" max="512"></div>',
)
replace_exact(
    "combined_refactor/index.html",
    '<div class="formrow"><label>测速并发</label><input class="input" id="speedThreads" type="number" value="1" min="1" max="2"></div>',
    '<div class="formrow"><label>测速并发</label><input class="input" id="speedThreads" type="number" value="1" min="1" max="16"></div>\n          <div class="note">并发提示：普通测试默认 8，64 以上会明显增加连接与 CPU 占用；测速默认 1，建议按机器性能逐步提高。</div>',
)
replace_exact(
    "combined_refactor/index.html",
    '轻量模式默认 8 并发、每 IP 仅测试 1 次；测速默认单线程并限制单节点下载量。',
    '轻量模式默认 8 并发、每 IP 仅测试 1 次；高性能机器可在高级设置提高并发，测速默认单线程。',
)
replace_exact(
    "combined_refactor/index.html",
    "workers=Math.max(1,Math.min(2,num($('speedThreads').value)||1))",
    "workers=Math.max(1,Math.min(16,num($('speedThreads').value)||1))",
)
replace_exact(
    "combined_refactor/index.html",
    "threads:Math.max(1,Math.min(16,Number($('threads').value||8)))",
    "threads:Math.max(1,Math.min(512,Number($('threads').value||8)))",
)
replace_exact(
    "combined_refactor/index.html",
    "if(c.version===4&&c.threads) $('threads').value=Math.max(1,Math.min(16,num(c.threads))); else $('threads').value=8;",
    "if(c.version===4&&c.threads) $('threads').value=Math.max(1,Math.min(512,num(c.threads))); else $('threads').value=8;",
)
replace_exact(
    "combined_refactor/index.html",
    "if(c.version===4&&c.speedThreads) $('speedThreads').value=Math.max(1,Math.min(2,num(c.speedThreads))); else $('speedThreads').value=1;",
    "if(c.version===4&&c.speedThreads) $('speedThreads').value=Math.max(1,Math.min(16,num(c.speedThreads))); else $('speedThreads').value=1;",
)

# Backend safeguards: generous ceilings to prevent accidental absurd values only.
replace_exact(
    "combined_refactor/proxy_local.go",
    "threads := clampProxyInt(req.Threads, 8, 1, 16)",
    "threads := clampProxyInt(req.Threads, 8, 1, 512)",
)
replace_exact(
    "combined_refactor/server.go",
    "\t\t\tif params.SpeedTest > 2 {\n\t\t\t\tparams.SpeedTest = 2\n\t\t\t}",
    "\t\t\tif params.SpeedTest > 16 {\n\t\t\t\tparams.SpeedTest = 16\n\t\t\t}",
)

# Tests: preserve manual values below the ceiling and assert the safety ceiling.
replace_exact(
    "combined_refactor/proxy_local_test.go",
    "if cfg.Attempts != 3 || cfg.Threads != 16 || cfg.Timeout != 7000000000 {",
    "if cfg.Attempts != 3 || cfg.Threads != 60 || cfg.Timeout != 7000000000 {",
)
replace_exact(
    "combined_refactor/proxy_local_test.go",
    "}\n\nfunc TestClassifyRequiresHTTPForEligible",
    "}\n\nfunc TestNormalizeProxyConfigCapsExtremeConcurrency(t *testing.T) {\n\tcfg := normalizeProxyConfig(proxyLocalTaskRequest{Threads: 9999})\n\tif cfg.Threads != 512 {\n\t\tt.Fatalf(\"extreme concurrency must be capped at 512, got %d\", cfg.Threads)\n\t}\n}\n\nfunc TestClassifyRequiresHTTPForEligible",
)

print("V4 concurrency limits finalized")
# trigger-finalize
