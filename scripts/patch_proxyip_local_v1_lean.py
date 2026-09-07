from pathlib import Path

root = Path('.')
go = root / 'combined_refactor'

# Make the local Web product genuinely local/lean at startup: no geo probe,
# no speed-source probe, and no release lookup just for opening the UI.
# This helper is intentionally idempotent because CI may run it on an already-patched branch.
server_path = go / 'server.go'
server = server_path.read_text(encoding='utf-8')
lean_marker = '"mode":    "proxy-local"'
if lean_marker not in server:
    start = server.find('\tcfCountry := ""')
    end = server.find('\n\tsafeHandler := func', start)
    if start < 0 or end < 0:
        raise SystemExit('server startup probe block not found and lean marker missing')
    replacement = '''\tsession.sendWSMessage("init_config", map[string]interface{}{
\t\t"version": appVersion,
\t\t"mode":    "proxy-local",
\t})
\tif backgroundSession := currentBackgroundTaskSession(); backgroundSession != nil {
\t\tsession.sendWSMessage("background_task_found", backgroundSession.backgroundSummary())
\t}
'''
    server = server[:start] + replacement + server[end:]
    server_path.write_text(server, encoding='utf-8')

main_path = go / 'main.go'
main = main_path.read_text(encoding='utf-8')
old_speed = '''\tstartupSpeedTestURL := speedTestURL
\tif !cliCfg.enabled {
\t\tctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
\t\tresolvedSpeedURL, speedISP, err := resolveStartupSpeedTestURL(ctx, speedTestURL)
\t\tcancel()
\t\tif err != nil {
\t\t\trecordDebugError("speed_isp_check", err.Error())
\t\t} else {
\t\t\tstartupSpeedTestURL = resolvedSpeedURL
\t\t\trecordDebugByLevel("all", "speed_isp_check", fmt.Sprintf("startup asn=%d org=%s mobile=%v selected=%s", speedISP.ASN, speedISP.ASOrganization, isChinaMobileISP(speedISP), currentAutoSpeedURLDefault()))
\t\t}
\t}
'''
if old_speed in main:
    main = main.replace(old_speed, '', 1)
elif 'startupSpeedTestURL :=' in main:
    raise SystemExit('unexpected startup speed probe shape')

old_locations = '\tinitLocations()\n\tif cliCfg.enabled {'
new_locations = '\tif cliCfg.enabled {\n\t\tinitLocations()'
if old_locations in main:
    main = main.replace(old_locations, new_locations, 1)
elif new_locations not in main:
    raise SystemExit('main initLocations block not found')

main = main.replace('\tgo checkAndPrintUpdate("")\n', '', 1)
if '\tfmt.Printf("当前测速网址: %s\\n", startupSpeedTestURL)\n' in main:
    main = main.replace('\tfmt.Printf("当前测速网址: %s\\n", startupSpeedTestURL)\n', '\tfmt.Println("测速策略: 精准模式按需启用，不在启动时联网探测")\n', 1)
elif '测速策略: 精准模式按需启用，不在启动时联网探测' not in main:
    raise SystemExit('main speed strategy output not found')

geo_block = '''\tif skipGeoCheck {
\t\tfmt.Println("地区验证: 已跳过")
\t} else {
\t\tfmt.Println("地区验证: 启用")
\t}
'''
main = main.replace(geo_block, '', 1)
main_path.write_text(main, encoding='utf-8')

# Add deterministic local-only tests for parser behavior and tolerant HTTP probing.
test_path = go / 'proxy_local_integration_test.go'
test_path.write_text(r'''package main

import (
    "context"
    "net"
    "strings"
    "testing"
    "time"
)

func TestParseProxyCandidatesDeduplicatesAndKeepsPorts(t *testing.T) {
    input := strings.Join([]string{
        "ProxyIP,Port",
        "1.2.3.4:443",
        "1.2.3.4:443",
        "5.6.7.8:443,2053,8443",
        "9.9.9.9 2083",
    }, "\n")
    got := parseProxyCandidates(input, 443)
    if len(got) != 5 {
        t.Fatalf("expected 5 unique candidates, got %d: %#v", len(got), got)
    }
    if got[1].Host != "5.6.7.8" || got[1].Port != 443 || got[3].Port != 8443 {
        t.Fatalf("multi-port parsing changed: %#v", got)
    }
}

func TestBlankSNIIsTCPOnlyAndRetained(t *testing.T) {
    cfg := normalizeProxyConfig(proxyLocalTaskRequest{EnableTLS: true, Mode: "standard"})
    r := proxyLocalResult{Attempts: cfg.Attempts, TCPSuccesses: 2, TCPMS: 40}
    classifyProxyResult(&r, cfg, 0)
    if r.Status != "edge" || r.SuccessRate != 66 {
        t.Fatalf("blank SNI candidate should be retained as edge, got %#v", r)
    }
}

func TestHTTP403WithCloudflareHeadersIsNotRejected(t *testing.T) {
    ln, err := net.Listen("tcp", "127.0.0.1:0")
    if err != nil {
        t.Fatal(err)
    }
    defer ln.Close()
    done := make(chan struct{})
    go func() {
        defer close(done)
        conn, err := ln.Accept()
        if err != nil {
            return
        }
        defer conn.Close()
        buf := make([]byte, 4096)
        _, _ = conn.Read(buf)
        _, _ = conn.Write([]byte("HTTP/1.1 403 Forbidden\r\nServer: cloudflare\r\nCF-Ray: local-test\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"))
    }()

    host, portText, err := net.SplitHostPort(ln.Addr().String())
    if err != nil {
        t.Fatal(err)
    }
    port, ok := parsePortForTest(portText)
    if !ok {
        t.Fatalf("bad test port: %s", portText)
    }
    cfg := proxyProbeConfig{Host: "example.com", Path: "/cdn-cgi/trace", EnableTLS: false, Attempts: 1, Timeout: 2 * time.Second}
    ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
    defer cancel()
    attempt := probeProxyOnce(ctx, proxyCandidate{Host: host, Port: port}, cfg)
    <-done
    if !attempt.TCP || !attempt.HTTP || !attempt.CF || !attempt.Strong || attempt.HTTPCode != 403 {
        t.Fatalf("403 Cloudflare response should be retained as valid evidence: %#v", attempt)
    }
}

func parsePortForTest(value string) (int, bool) {
    n := 0
    if value == "" {
        return 0, false
    }
    for _, ch := range value {
        if ch < '0' || ch > '9' {
            return 0, false
        }
        n = n*10 + int(ch-'0')
    }
    return n, n > 0 && n <= 65535
}
''', encoding='utf-8')

print('Lean startup + local integration tests applied')
