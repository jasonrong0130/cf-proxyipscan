from pathlib import Path
import base64, gzip

ROOT = Path(__file__).resolve().parents[1]

INDEX_GZ_B64 = "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"

index_path = ROOT / "combined_refactor" / "index.html"
index_path.write_bytes(gzip.decompress(base64.b64decode(INDEX_GZ_B64)))

proxy_path = ROOT / "combined_refactor" / "proxy_local.go"
proxy = proxy_path.read_text(encoding="utf-8")
old_classify = '''func classifyProxyResult(result *proxyLocalResult, cfg proxyProbeConfig, _ int) {
\tif result.Attempts <= 0 {
\t\tresult.Attempts = 1
\t}

\tswitch {
\tcase result.HTTPSuccesses > 0:
\t\tresult.Stage = "http"
\tcase result.TLSSuccesses > 0:
\t\tresult.Stage = "tls"
\tcase result.TCPSuccesses > 0:
\t\tresult.Stage = "tcp"
\tdefault:
\t\tresult.Stage = "failed"
\t}

\tsuccesses := result.HTTPSuccesses
\tif (cfg.EnableTLS && cfg.SNI == "") || (!cfg.EnableTLS && cfg.Host == "") {
\t\tsuccesses = result.TCPSuccesses
\t}
\tresult.SuccessRate = int(float64(successes) / float64(result.Attempts) * 100)

\tif result.Stage == "failed" {
\t\tresult.Status = "failed"
\t\tif result.Error == "" {
\t\t\tresult.Error = "TCP 不可达"
\t\t}
\t\treturn
\t}
\tresult.Status = "success"
\tif cfg.EnableTLS && cfg.SNI == "" && result.Error == "" {
\t\tresult.Error = "未填写 SNI，仅完成 TCP 测试"
\t}
}
'''
new_classify = '''func classifyProxyResult(result *proxyLocalResult, cfg proxyProbeConfig, _ int) {
\tif result.Attempts <= 0 {
\t\tresult.Attempts = 1
\t}

\tswitch {
\tcase result.HTTPSuccesses > 0:
\t\tresult.Stage = "http"
\tcase result.TLSSuccesses > 0:
\t\tresult.Stage = "tls"
\tcase result.TCPSuccesses > 0:
\t\tresult.Stage = "tcp"
\tdefault:
\t\tresult.Stage = "failed"
\t}

\tresult.SuccessRate = int(float64(result.HTTPSuccesses) / float64(result.Attempts) * 100)
\tif result.HTTPSuccesses > 0 {
\t\tresult.Status = "success"
\t\treturn
\t}

\tresult.Status = "failed"
\tif result.Error != "" {
\t\treturn
\t}
\tswitch result.Stage {
\tcase "tls":
\t\tresult.Error = "TLS 已连接，但未收到 HTTP 响应"
\tcase "tcp":
\t\tresult.Error = "TCP 可达，但 TLS / HTTP 链路未完成"
\tdefault:
\t\tresult.Error = "TCP 不可达"
\t}
}
'''
if old_classify not in proxy:
    raise SystemExit("classifyProxyResult source block not found")
proxy = proxy.replace(old_classify, new_classify)

old_start = '''func runProxyLocalTask(ctx context.Context, session *appSession, req proxyLocalTaskRequest) {
\tcfg := normalizeProxyConfig(req)
\tcandidates := parseProxyCandidates(req.FileContent, req.FallbackPort)
'''
new_start = '''func runProxyLocalTask(ctx context.Context, session *appSession, req proxyLocalTaskRequest) {
\tcfg := normalizeProxyConfig(req)
\tif cfg.SNI == "" {
\t\tsession.sendWSMessage("error", "请先填写实际使用的 SNI")
\t\treturn
\t}
\tcandidates := parseProxyCandidates(req.FileContent, req.FallbackPort)
'''
if old_start not in proxy:
    raise SystemExit("runProxyLocalTask source block not found")
proxy = proxy.replace(old_start, new_start)

old_blank_log = '''\n\tif cfg.EnableTLS && cfg.SNI == "" {
\t\tsession.sendWSMessage("log", "SNI 为空：本轮只做 TCP 本地测试，不使用固定公共域名代替真实 SNI。")
\t}
'''
proxy = proxy.replace(old_blank_log, "\n")
old_phase = '''\tphaseText := "真实 SNI / 本地链路测试中"
\tif cfg.EnableTLS && cfg.SNI == "" {
\t\tphaseText = "TCP 本地测试中"
\t}
'''
if old_phase in proxy:
    proxy = proxy.replace(old_phase, '\tphaseText := "真实 SNI / 本地链路测试中"\n')
proxy_path.write_text(proxy, encoding="utf-8")

test_path = ROOT / "combined_refactor" / "proxy_local_test.go"
test = test_path.read_text(encoding="utf-8")
test = test.replace('''func TestClassifyIsMetricOnly(t *testing.T) {
\tcfg := proxyProbeConfig{SNI: "example.com", Host: "example.com", EnableTLS: true}
\tresult := proxyLocalResult{Attempts: 1, TCPSuccesses: 1, TLSSuccesses: 1, HTTPSuccesses: 0, TCPMS: 35}
\tclassifyProxyResult(&result, cfg, 0)
\tif result.Status != "success" || result.Stage != "tls" {
\t\tt.Fatalf("reachable candidate should report factual stage, got %#v", result)
\t}
}
''','''func TestClassifyRequiresHTTPForEligible(t *testing.T) {
\tcfg := proxyProbeConfig{SNI: "example.com", Host: "example.com", EnableTLS: true}
\tresult := proxyLocalResult{Attempts: 1, TCPSuccesses: 1, TLSSuccesses: 1, HTTPSuccesses: 0, TCPMS: 35}
\tclassifyProxyResult(&result, cfg, 0)
\tif result.Status != "failed" || result.Stage != "tls" || result.SuccessRate != 0 {
\t\tt.Fatalf("TLS-only candidate must not be marked eligible, got %#v", result)
\t}
}
''')
test_path.write_text(test, encoding="utf-8")

integration_path = ROOT / "combined_refactor" / "proxy_local_integration_test.go"
integration = integration_path.read_text(encoding="utf-8")
integration = integration.replace('''func TestBlankSNIIsTCPOnlyAndReportedFactually(t *testing.T) {
\tcfg := normalizeProxyConfig(proxyLocalTaskRequest{EnableTLS: true})
\tr := proxyLocalResult{Attempts: cfg.Attempts, TCPSuccesses: 1, TCPMS: 40}
\tclassifyProxyResult(&r, cfg, 0)
\tif r.Status != "success" || r.Stage != "tcp" || r.SuccessRate != 100 {
\t\tt.Fatalf("blank SNI candidate should report TCP reachability, got %#v", r)
\t}
}
''','''func TestTCPOnlyIsNotEligible(t *testing.T) {
\tcfg := normalizeProxyConfig(proxyLocalTaskRequest{EnableTLS: true, SNI: "example.com"})
\tr := proxyLocalResult{Attempts: cfg.Attempts, TCPSuccesses: 1, TCPMS: 40}
\tclassifyProxyResult(&r, cfg, 0)
\tif r.Status != "failed" || r.Stage != "tcp" || r.SuccessRate != 0 {
\t\tt.Fatalf("TCP-only candidate must not be marked eligible, got %#v", r)
\t}
}
''')
integration = integration.replace('required := []string{"CF优选IP筛选器", "start_proxy_task", "example.com", "Host 默认跟随 SNI", "一键测速", "pageSize"}',
                                  'required := []string{"CF优选IP筛选器", "start_proxy_task", "example.com", "Host 默认跟随 SNI", "一键测速", "停止测速", "请先填写实际使用的 SNI", "pageSize"}')
integration_path.write_text(integration, encoding="utf-8")

print("Applied agreed V3 UI, eligibility logic, SNI guard, stop-speed UI, and tests")
