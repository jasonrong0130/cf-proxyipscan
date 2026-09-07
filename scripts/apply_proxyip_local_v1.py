from pathlib import Path

ROOT = Path('.')
GO_DIR = ROOT / 'combined_refactor'

proxy_go = r'''package main

import (
    "bufio"
    "context"
    "crypto/tls"
    "fmt"
    "io"
    "net"
    "sort"
    "strconv"
    "strings"
    "sync"
    "time"
)

type proxyLocalTaskRequest struct {
    FileName     string `json:"fileName"`
    FileContent  string `json:"fileContent"`
    FallbackPort int    `json:"fallbackPort"`
    SNI          string `json:"sni"`
    Host         string `json:"host"`
    Path         string `json:"path"`
    EnableTLS    bool   `json:"enableTLS"`
    Mode         string `json:"mode"`
    Threads      int    `json:"threads"`
    TimeoutMS    int    `json:"timeoutMs"`
    Insecure     bool   `json:"insecure"`
    SpeedLimit   int    `json:"speedLimit"`
}

type proxyCandidate struct {
    Host string
    Port int
}

type proxyProbeConfig struct {
    SNI       string
    Host      string
    Path      string
    EnableTLS bool
    Insecure  bool
    Attempts  int
    Threads   int
    Timeout   time.Duration
    Mode      string
    SpeedLimit int
}

type proxyProbeAttempt struct {
    TCP      bool
    TLS      bool
    HTTP     bool
    Strong   bool
    TCPMS    int64
    TLSMS    int64
    TTFBMS   int64
    HTTPCode int
    CF       bool
    Colo     string
    Loc      string
    ExitIP   string
    Error    string
}

type proxyLocalResult struct {
    IP             string  `json:"ip"`
    Port           int     `json:"port"`
    Endpoint       string  `json:"endpoint"`
    Status         string  `json:"status"`
    SuccessRate    int     `json:"successRate"`
    Attempts       int     `json:"attempts"`
    TCPSuccesses   int     `json:"tcpSuccesses"`
    TLSSuccesses   int     `json:"tlsSuccesses"`
    HTTPSuccesses  int     `json:"httpSuccesses"`
    TCPMS          int64   `json:"tcpMs"`
    TLSMS          int64   `json:"tlsMs"`
    TTFBMS         int64   `json:"ttfbMs"`
    HTTPStatus     int     `json:"httpStatus"`
    CFConfirmed    bool    `json:"cfConfirmed"`
    Colo           string  `json:"colo,omitempty"`
    Loc            string  `json:"loc,omitempty"`
    ExitIP         string  `json:"exitIp,omitempty"`
    Score          float64 `json:"score"`
    SpeedMbps      float64 `json:"speedMbps,omitempty"`
    Error          string  `json:"error,omitempty"`
}

type proxyLocalSummary struct {
    Total        int `json:"total"`
    TCPReachable int `json:"tcpReachable"`
    RealUsable   int `json:"realUsable"`
    Excellent    int `json:"excellent"`
    Usable       int `json:"usable"`
    Edge         int `json:"edge"`
    Failed       int `json:"failed"`
}

func clampProxyInt(value, fallback, minValue, maxValue int) int {
    if value <= 0 {
        value = fallback
    }
    if value < minValue {
        return minValue
    }
    if value > maxValue {
        return maxValue
    }
    return value
}

func normalizeProxyHost(value string) string {
    value = strings.TrimSpace(value)
    value = strings.TrimPrefix(value, "https://")
    value = strings.TrimPrefix(value, "http://")
    if slash := strings.IndexByte(value, '/'); slash >= 0 {
        value = value[:slash]
    }
    if host, _, err := net.SplitHostPort(value); err == nil {
        value = host
    }
    return strings.Trim(strings.TrimSpace(value), "[]")
}

func normalizeProxyPath(value string) string {
    value = strings.TrimSpace(value)
    if value == "" {
        return "/cdn-cgi/trace"
    }
    if !strings.HasPrefix(value, "/") {
        value = "/" + value
    }
    return value
}

func normalizeProxyConfig(req proxyLocalTaskRequest) proxyProbeConfig {
    mode := strings.ToLower(strings.TrimSpace(req.Mode))
    attempts, threads, timeoutMS := 3, 30, 5000
    switch mode {
    case "fast":
        attempts, threads, timeoutMS = 2, 50, 3500
    case "precise":
        attempts, threads, timeoutMS = 5, 20, 6500
    default:
        mode = "standard"
    }
    threads = clampProxyInt(req.Threads, threads, 1, 100)
    timeoutMS = clampProxyInt(req.TimeoutMS, timeoutMS, 1500, 15000)
    speedLimit := req.SpeedLimit
    if speedLimit < 0 {
        speedLimit = 0
    }
    if speedLimit == 0 && mode == "precise" {
        speedLimit = 10
    }
    if speedLimit > 50 {
        speedLimit = 50
    }
    sni := normalizeProxyHost(req.SNI)
    host := normalizeProxyHost(req.Host)
    if host == "" {
        host = sni
    }
    return proxyProbeConfig{
        SNI: sni,
        Host: host,
        Path: normalizeProxyPath(req.Path),
        EnableTLS: req.EnableTLS,
        Insecure: req.Insecure,
        Attempts: attempts,
        Threads: threads,
        Timeout: time.Duration(timeoutMS) * time.Millisecond,
        Mode: mode,
        SpeedLimit: speedLimit,
    }
}

func parseProxyEndpoint(value string, fallbackPort int) (proxyCandidate, bool) {
    value = strings.TrimSpace(strings.Trim(value, "\"'"))
    if value == "" {
        return proxyCandidate{}, false
    }
    if strings.HasPrefix(value, "[") {
        if host, portText, err := net.SplitHostPort(value); err == nil {
            port, err := strconv.Atoi(portText)
            if err == nil && port > 0 && port <= 65535 {
                return proxyCandidate{Host: strings.Trim(host, "[]"), Port: port}, true
            }
        }
    }
    if strings.Count(value, ":") == 1 {
        parts := strings.SplitN(value, ":", 2)
        if port, err := strconv.Atoi(strings.TrimSpace(parts[1])); err == nil && port > 0 && port <= 65535 {
            return proxyCandidate{Host: strings.TrimSpace(parts[0]), Port: port}, true
        }
    }
    if net.ParseIP(strings.Trim(value, "[]")) != nil || !strings.ContainsAny(value, " \t,") {
        if fallbackPort > 0 && fallbackPort <= 65535 {
            return proxyCandidate{Host: strings.Trim(value, "[]"), Port: fallbackPort}, true
        }
    }
    return proxyCandidate{}, false
}

func parseProxyCandidates(raw string, fallbackPort int) []proxyCandidate {
    fallbackPort = clampProxyInt(fallbackPort, 443, 1, 65535)
    raw = strings.ReplaceAll(raw, "\r\n", "\n")
    raw = strings.ReplaceAll(raw, "\r", "\n")
    scanner := bufio.NewScanner(strings.NewReader(raw))
    scanner.Buffer(make([]byte, 64*1024), 2*1024*1024)
    seen := make(map[string]struct{})
    result := make([]proxyCandidate, 0, 256)
    add := func(candidate proxyCandidate) {
        candidate.Host = strings.TrimSpace(strings.Trim(candidate.Host, "[]"))
        if candidate.Host == "" || candidate.Port <= 0 || candidate.Port > 65535 {
            return
        }
        key := strings.ToLower(candidate.Host) + ":" + strconv.Itoa(candidate.Port)
        if _, ok := seen[key]; ok {
            return
        }
        seen[key] = struct{}{}
        result = append(result, candidate)
    }
    for scanner.Scan() {
        line := strings.TrimSpace(strings.TrimPrefix(scanner.Text(), "\ufeff"))
        if line == "" || strings.HasPrefix(line, "#") || strings.HasPrefix(line, "//") {
            continue
        }
        lower := strings.ToLower(line)
        if strings.Contains(lower, "ip") && strings.Contains(lower, "port") && strings.Contains(line, ",") {
            continue
        }
        // Explicit multi-port syntax: 1.2.3.4:443,8443,2053
        if strings.Count(line, ":") == 1 && strings.Contains(line, ",") {
            first := strings.IndexByte(line, ':')
            host := strings.TrimSpace(line[:first])
            ports := strings.Split(line[first+1:], ",")
            allPorts := host != "" && len(ports) > 1
            parsedPorts := make([]int, 0, len(ports))
            for _, p := range ports {
                port, err := strconv.Atoi(strings.TrimSpace(p))
                if err != nil || port <= 0 || port > 65535 {
                    allPorts = false
                    break
                }
                parsedPorts = append(parsedPorts, port)
            }
            if allPorts {
                for _, port := range parsedPorts {
                    add(proxyCandidate{Host: host, Port: port})
                }
                continue
            }
        }
        if candidate, ok := parseProxyEndpoint(line, fallbackPort); ok {
            add(candidate)
            continue
        }
        // CSV: endpoint,... OR ip,port,...
        if strings.Contains(line, ",") {
            cells := strings.Split(line, ",")
            for i := range cells {
                cells[i] = strings.TrimSpace(cells[i])
            }
            if len(cells) > 0 {
                if candidate, ok := parseProxyEndpoint(cells[0], fallbackPort); ok {
                    if len(cells) > 1 && !strings.Contains(cells[0], ":") {
                        if port, err := strconv.Atoi(cells[1]); err == nil && port > 0 && port <= 65535 {
                            candidate.Port = port
                        }
                    }
                    add(candidate)
                    continue
                }
            }
        }
        fields := strings.Fields(line)
        if len(fields) >= 2 {
            if port, err := strconv.Atoi(fields[1]); err == nil && port > 0 && port <= 65535 {
                add(proxyCandidate{Host: strings.Trim(fields[0], "[]"), Port: port})
            }
        }
    }
    return result
}

func parseHTTPStatusLine(line string) int {
    fields := strings.Fields(strings.TrimSpace(line))
    if len(fields) < 2 || !strings.HasPrefix(strings.ToUpper(fields[0]), "HTTP/") {
        return 0
    }
    code, _ := strconv.Atoi(fields[1])
    if code < 100 || code > 599 {
        return 0
    }
    return code
}

func probeProxyOnce(ctx context.Context, candidate proxyCandidate, cfg proxyProbeConfig) proxyProbeAttempt {
    attempt := proxyProbeAttempt{}
    dialer := net.Dialer{Timeout: cfg.Timeout}
    address := net.JoinHostPort(candidate.Host, strconv.Itoa(candidate.Port))
    tcpStart := time.Now()
    rawConn, err := dialer.DialContext(ctx, "tcp", address)
    if err != nil {
        attempt.Error = "TCP: " + err.Error()
        return attempt
    }
    defer rawConn.Close()
    attempt.TCP = true
    attempt.TCPMS = time.Since(tcpStart).Milliseconds()
    _ = rawConn.SetDeadline(time.Now().Add(cfg.Timeout))

    // SNI 留空时只做本地 TCP 可达性筛选，避免使用固定公共域名误杀 ProxyIP。
    if cfg.EnableTLS && cfg.SNI == "" {
        return attempt
    }

    conn := net.Conn(rawConn)
    if cfg.EnableTLS {
        tlsStart := time.Now()
        tlsConn := tls.Client(rawConn, &tls.Config{
            ServerName:         cfg.SNI,
            RootCAs:            rootCAPool(),
            InsecureSkipVerify: cfg.Insecure, // 用户高级设置显式开启时使用
            NextProtos:         []string{"http/1.1"},
            MinVersion:         tls.VersionTLS12,
        })
        if err := tlsConn.HandshakeContext(ctx); err != nil {
            attempt.Error = "TLS: " + err.Error()
            return attempt
        }
        attempt.TLS = true
        attempt.TLSMS = time.Since(tlsStart).Milliseconds()
        conn = tlsConn
    }

    host := cfg.Host
    if host == "" {
        host = cfg.SNI
    }
    if host == "" {
        return attempt
    }

    reqStart := time.Now()
    request := fmt.Sprintf("GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: ProxyIP-Optimizer/%s\r\nAccept: */*\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n", cfg.Path, host, appVersion)
    if _, err := io.WriteString(conn, request); err != nil {
        attempt.Error = "HTTP write: " + err.Error()
        return attempt
    }

    reader := bufio.NewReaderSize(conn, 16*1024)
    statusLine, err := reader.ReadString('\n')
    if err != nil {
        attempt.Error = "HTTP response: " + err.Error()
        return attempt
    }
    attempt.TTFBMS = time.Since(reqStart).Milliseconds()
    attempt.HTTPCode = parseHTTPStatusLine(statusLine)
    if attempt.HTTPCode == 0 {
        attempt.Error = "HTTP: invalid status line"
        return attempt
    }

    headers := make(map[string]string)
    for {
        line, err := reader.ReadString('\n')
        if err != nil {
            attempt.Error = "HTTP headers: " + err.Error()
            return attempt
        }
        line = strings.TrimRight(line, "\r\n")
        if line == "" {
            break
        }
        if colon := strings.IndexByte(line, ':'); colon > 0 {
            key := strings.ToLower(strings.TrimSpace(line[:colon]))
            value := strings.TrimSpace(line[colon+1:])
            headers[key] = value
        }
    }

    attempt.HTTP = true
    server := strings.ToLower(headers["server"])
    attempt.CF = server == "cloudflare" || strings.Contains(server, "cloudflare") || strings.TrimSpace(headers["cf-ray"]) != ""
    attempt.Strong = attempt.CF || (attempt.HTTPCode >= 200 && attempt.HTTPCode < 400)

    if strings.Contains(cfg.Path, "cdn-cgi/trace") || strings.Contains(strings.ToLower(headers["content-type"]), "text/plain") {
        readWindow := 800 * time.Millisecond
        if cfg.Timeout < readWindow {
            readWindow = cfg.Timeout
        }
        _ = conn.SetReadDeadline(time.Now().Add(readWindow))
        body, _ := io.ReadAll(io.LimitReader(reader, 16*1024))
        trace := parseTraceResponse(string(body))
        if trace["colo"] != "" {
            attempt.Colo = trace["colo"]
            attempt.CF = true
        }
        attempt.Loc = trace["loc"]
        attempt.ExitIP = trace["ip"]
    }
    return attempt
}

func averageInt64(sum int64, count int) int64 {
    if count <= 0 {
        return 0
    }
    return sum / int64(count)
}

func classifyProxyResult(result *proxyLocalResult, cfg proxyProbeConfig, strongSuccesses int) {
    if result.TCPSuccesses == 0 {
        result.Status = "failed"
        result.Score = 0
        if result.Error == "" {
            result.Error = "TCP 不可达"
        }
        return
    }
    if cfg.SNI == "" && cfg.EnableTLS {
        result.Status = "edge"
        result.SuccessRate = int(float64(result.TCPSuccesses) / float64(result.Attempts) * 100)
        result.Score = 30 + float64(result.SuccessRate)*0.35 - float64(result.TCPMS)/25
        if result.Score < 1 {
            result.Score = 1
        }
        result.Error = "未填写 SNI，仅完成 TCP 本地筛选"
        return
    }

    result.SuccessRate = int(float64(result.HTTPSuccesses) / float64(result.Attempts) * 100)
    if result.HTTPSuccesses == result.Attempts && strongSuccesses > 0 && result.TTFBMS > 0 && result.TTFBMS <= 650 {
        result.Status = "excellent"
    } else if result.HTTPSuccesses > 0 && result.SuccessRate >= 50 {
        result.Status = "usable"
    } else {
        // TCP/TLS 已经能够到达但 HTTP 探针未满足时保留为边缘候选，不再一票误杀。
        result.Status = "edge"
    }

    score := float64(result.SuccessRate) * 0.62
    tcpRate := float64(result.TCPSuccesses) / float64(result.Attempts) * 100
    score += tcpRate * 0.18
    if result.CFConfirmed {
        score += 8
    }
    if result.TCPMS > 0 {
        score += 8 - minFloat(8, float64(result.TCPMS)/40)
    }
    if result.TTFBMS > 0 {
        score += 8 - minFloat(8, float64(result.TTFBMS)/120)
    }
    if result.Status == "edge" {
        score = minFloat(score, 59)
    }
    if score < 1 {
        score = 1
    }
    if score > 100 {
        score = 100
    }
    result.Score = float64(int(score*10)) / 10
}

func minFloat(a, b float64) float64 {
    if a < b {
        return a
    }
    return b
}

func probeProxyCandidate(ctx context.Context, candidate proxyCandidate, cfg proxyProbeConfig) proxyLocalResult {
    result := proxyLocalResult{
        IP: candidate.Host,
        Port: candidate.Port,
        Endpoint: net.JoinHostPort(candidate.Host, strconv.Itoa(candidate.Port)),
        Attempts: cfg.Attempts,
    }
    var tcpSum, tlsSum, ttfbSum int64
    strongSuccesses := 0
    lastError := ""
    for i := 0; i < cfg.Attempts; i++ {
        if ctx.Err() != nil {
            lastError = "任务已终止"
            break
        }
        attempt := probeProxyOnce(ctx, candidate, cfg)
        if attempt.TCP {
            result.TCPSuccesses++
            tcpSum += attempt.TCPMS
        }
        if attempt.TLS {
            result.TLSSuccesses++
            tlsSum += attempt.TLSMS
        }
        if attempt.HTTP {
            result.HTTPSuccesses++
            ttfbSum += attempt.TTFBMS
            result.HTTPStatus = attempt.HTTPCode
        }
        if attempt.Strong {
            strongSuccesses++
        }
        if attempt.CF {
            result.CFConfirmed = true
        }
        if result.Colo == "" && attempt.Colo != "" {
            result.Colo = attempt.Colo
        }
        if result.Loc == "" && attempt.Loc != "" {
            result.Loc = attempt.Loc
        }
        if result.ExitIP == "" && attempt.ExitIP != "" {
            result.ExitIP = attempt.ExitIP
        }
        if attempt.Error != "" {
            lastError = attempt.Error
        }
    }
    result.TCPMS = averageInt64(tcpSum, result.TCPSuccesses)
    result.TLSMS = averageInt64(tlsSum, result.TLSSuccesses)
    result.TTFBMS = averageInt64(ttfbSum, result.HTTPSuccesses)
    result.Error = lastError
    classifyProxyResult(&result, cfg, strongSuccesses)
    return result
}

func proxySummary(results []proxyLocalResult) proxyLocalSummary {
    summary := proxyLocalSummary{Total: len(results)}
    for _, result := range results {
        if result.TCPSuccesses > 0 {
            summary.TCPReachable++
        }
        switch result.Status {
        case "excellent":
            summary.Excellent++
            summary.RealUsable++
        case "usable":
            summary.Usable++
            summary.RealUsable++
        case "edge":
            summary.Edge++
        default:
            summary.Failed++
        }
    }
    return summary
}

func proxyResultLess(a, b proxyLocalResult) bool {
    rank := map[string]int{"excellent": 0, "usable": 1, "edge": 2, "failed": 3}
    if rank[a.Status] != rank[b.Status] {
        return rank[a.Status] < rank[b.Status]
    }
    if a.Score != b.Score {
        return a.Score > b.Score
    }
    if a.SpeedMbps != b.SpeedMbps {
        return a.SpeedMbps > b.SpeedMbps
    }
    if a.TTFBMS != b.TTFBMS {
        if a.TTFBMS == 0 {
            return false
        }
        if b.TTFBMS == 0 {
            return true
        }
        return a.TTFBMS < b.TTFBMS
    }
    return a.TCPMS < b.TCPMS
}

func runProxyReferenceSpeed(ctx context.Context, session *appSession, results []proxyLocalResult, cfg proxyProbeConfig) []proxyLocalResult {
    if cfg.Mode != "precise" || cfg.SpeedLimit <= 0 {
        return results
    }
    eligible := make([]int, 0, len(results))
    for i := range results {
        if results[i].Status == "excellent" || results[i].Status == "usable" {
            eligible = append(eligible, i)
        }
    }
    sort.Slice(eligible, func(i, j int) bool { return proxyResultLess(results[eligible[i]], results[eligible[j]]) })
    if len(eligible) > cfg.SpeedLimit {
        eligible = eligible[:cfg.SpeedLimit]
    }
    if len(eligible) == 0 {
        return results
    }

    testURL := speedTestURL
    if isAutoSpeedURL(testURL) {
        resolved, _, err := resolveStartupSpeedTestURL(ctx, speedTestURL)
        if err == nil && strings.TrimSpace(resolved) != "" {
            testURL = resolved
        }
    }
    session.sendWSMessage("proxy_progress", map[string]interface{}{"phase": "speed", "current": 0, "total": len(eligible), "text": "参考测速中（测速失败不会淘汰节点）"})
    for pos, idx := range eligible {
        if ctx.Err() != nil {
            break
        }
        speedKB, speedErr := runNSBDownloadSpeed(ctx, results[idx].IP, results[idx].Port, cfg.EnableTLS, testURL)
        if speedErr == "" && speedKB > 0 {
            results[idx].SpeedMbps = float64(int((speedKB*8/1024)*10)) / 10
            results[idx].Score += minFloat(8, results[idx].SpeedMbps/80)
            if results[idx].Score > 100 {
                results[idx].Score = 100
            }
        }
        session.sendWSMessage("proxy_result", results[idx])
        session.sendWSMessage("proxy_progress", map[string]interface{}{"phase": "speed", "current": pos + 1, "total": len(eligible), "text": "参考测速中（测速失败不会淘汰节点）"})
    }
    return results
}

func runProxyLocalTask(ctx context.Context, session *appSession, req proxyLocalTaskRequest) {
    cfg := normalizeProxyConfig(req)
    candidates := parseProxyCandidates(req.FileContent, req.FallbackPort)
    if len(candidates) == 0 {
        session.sendWSMessage("error", "没有解析到有效的 IP:端口")
        return
    }
    if cfg.EnableTLS && cfg.SNI == "" {
        session.sendWSMessage("log", "SNI 为空：本轮只做 TCP 本地筛选，不会使用 speed.cloudflare.com 代替真实 SNI。")
    }
    session.sendWSMessage("proxy_started", map[string]interface{}{
        "total": len(candidates), "attempts": cfg.Attempts, "threads": cfg.Threads,
        "mode": cfg.Mode, "sniConfigured": cfg.SNI != "",
    })
    phaseText := "真实 SNI / 本地链路验证中"
    if cfg.SNI == "" && cfg.EnableTLS {
        phaseText = "TCP 本地可达性筛选中"
    }
    session.sendWSMessage("proxy_progress", map[string]interface{}{"phase": "probe", "current": 0, "total": len(candidates), "text": phaseText})

    results := make([]proxyLocalResult, len(candidates))
    jobs := make(chan int)
    var wg sync.WaitGroup
    var progressMu sync.Mutex
    processed := 0
    workerCount := cfg.Threads
    if workerCount > len(candidates) {
        workerCount = len(candidates)
    }
    for worker := 0; worker < workerCount; worker++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for idx := range jobs {
                if ctx.Err() != nil {
                    return
                }
                result := probeProxyCandidate(ctx, candidates[idx], cfg)
                results[idx] = result
                session.sendWSMessage("proxy_result", result)
                progressMu.Lock()
                processed++
                current := processed
                progressMu.Unlock()
                session.sendWSMessage("proxy_progress", map[string]interface{}{"phase": "probe", "current": current, "total": len(candidates), "text": phaseText})
            }
        }()
    }
    for idx := range candidates {
        select {
        case <-ctx.Done():
            close(jobs)
            wg.Wait()
            partial := make([]proxyLocalResult, 0, processed)
            for _, result := range results {
                if result.Endpoint != "" {
                    partial = append(partial, result)
                }
            }
            sort.Slice(partial, func(i, j int) bool { return proxyResultLess(partial[i], partial[j]) })
            session.sendWSMessage("proxy_complete", map[string]interface{}{"results": partial, "summary": proxySummary(partial), "partial": true})
            return
        case jobs <- idx:
        }
    }
    close(jobs)
    wg.Wait()

    results = runProxyReferenceSpeed(ctx, session, results, cfg)
    sort.Slice(results, func(i, j int) bool { return proxyResultLess(results[i], results[j]) })
    session.sendWSMessage("proxy_complete", map[string]interface{}{"results": results, "summary": proxySummary(results), "partial": ctx.Err() != nil})
}
'''

proxy_test = r'''package main

import "testing"

func TestParseProxyCandidates(t *testing.T) {
    input := "IP,Port\n1.2.3.4,443\n5.6.7.8:8443\n1.1.1.1\n9.9.9.9:443,2053\n"
    rows := parseProxyCandidates(input, 443)
    if len(rows) != 5 {
        t.Fatalf("expected 5 candidates, got %d: %#v", len(rows), rows)
    }
    if rows[0].Host != "1.2.3.4" || rows[0].Port != 443 {
        t.Fatalf("unexpected first row: %#v", rows[0])
    }
}

func TestNormalizeProxyConfigNoPersonalDefault(t *testing.T) {
    cfg := normalizeProxyConfig(proxyLocalTaskRequest{EnableTLS: true, Mode: "standard"})
    if cfg.SNI != "" || cfg.Host != "" {
        t.Fatalf("SNI/Host must remain blank by default: %#v", cfg)
    }
    if cfg.Path != "/cdn-cgi/trace" || cfg.Attempts != 3 {
        t.Fatalf("unexpected defaults: %#v", cfg)
    }
}

func TestClassifyKeepsBorderlineCandidate(t *testing.T) {
    cfg := proxyProbeConfig{SNI: "example.com", EnableTLS: true}
    result := proxyLocalResult{Attempts: 3, TCPSuccesses: 3, TLSSuccesses: 1, HTTPSuccesses: 0, TCPMS: 35}
    classifyProxyResult(&result, cfg, 0)
    if result.Status != "edge" {
        t.Fatalf("TLS/TCP reachable candidate should be kept as edge, got %s", result.Status)
    }
}

func TestClassifyHTTPResponseAsUsable(t *testing.T) {
    cfg := proxyProbeConfig{SNI: "example.com", EnableTLS: true}
    result := proxyLocalResult{Attempts: 3, TCPSuccesses: 3, TLSSuccesses: 2, HTTPSuccesses: 2, TCPMS: 35, TTFBMS: 110}
    classifyProxyResult(&result, cfg, 1)
    if result.Status != "usable" {
        t.Fatalf("expected usable, got %s", result.Status)
    }
}
'''

index_html = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ProxyIP Optimizer</title>
<style>
:root{--bg:#eef3fb;--glass:rgba(255,255,255,.60);--glass-strong:rgba(255,255,255,.78);--line:rgba(255,255,255,.78);--text:#162033;--muted:#6e7b91;--dark:#14243d;--blue:#2487ff;--green:#12a877;--orange:#f59e0b;--red:#ef4055;--shadow:0 18px 60px rgba(64,87,123,.12),inset 0 1px 0 rgba(255,255,255,.8);--radius:20px}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:var(--text)}body{background:radial-gradient(circle at 8% 12%,rgba(255,255,255,.96),transparent 30%),radial-gradient(circle at 86% 18%,rgba(183,214,255,.65),transparent 30%),radial-gradient(circle at 48% 100%,rgba(214,226,255,.8),transparent 40%),linear-gradient(135deg,#f7f9fd,#e7eef9 55%,#f8fbff);padding:22px}.shell{width:min(1500px,calc(100vw - 28px));margin:auto;border:1px solid rgba(255,255,255,.88);border-radius:24px;background:rgba(244,248,255,.56);box-shadow:0 28px 100px rgba(58,77,112,.18),inset 0 1px 0 #fff;backdrop-filter:blur(28px) saturate(155%);overflow:hidden}.titlebar{height:64px;display:flex;align-items:center;gap:14px;padding:0 22px;border-bottom:1px solid rgba(173,190,216,.28);background:rgba(255,255,255,.48);backdrop-filter:blur(28px)}.lights{display:flex;gap:7px}.lights i{width:12px;height:12px;border-radius:50%;display:block}.lights i:nth-child(1){background:#ff5f57}.lights i:nth-child(2){background:#febc2e}.lights i:nth-child(3){background:#28c840}.brandmark{width:38px;height:38px;border-radius:12px;background:linear-gradient(145deg,#20344f,#0c1628);display:grid;place-items:center;color:#fff;font-size:21px;box-shadow:inset 0 1px 1px rgba(255,255,255,.24),0 8px 24px rgba(21,37,62,.22)}.brand{line-height:1.1}.brand b{font-size:18px}.brand span{display:block;font-size:11px;color:var(--muted);margin-top:4px}.topnav{margin-left:auto;display:flex;gap:10px}.ghost{border:1px solid rgba(177,191,214,.48);background:rgba(255,255,255,.45);color:var(--text);border-radius:12px;padding:9px 13px;cursor:pointer;backdrop-filter:blur(14px)}.main{padding:22px 28px 30px}.hero h1{font-size:28px;margin:0 0 3px}.hero p{margin:0 0 18px;color:var(--muted);font-size:13px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:14px}.glass{background:var(--glass);border:1px solid var(--line);box-shadow:var(--shadow);backdrop-filter:blur(22px) saturate(150%);border-radius:var(--radius)}.stat{padding:16px 20px;display:flex;align-items:center;gap:14px}.stat .ico{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;font-size:21px;background:rgba(232,239,250,.78);box-shadow:inset 0 1px 0 #fff}.stat.green .ico{color:var(--green);background:rgba(218,249,238,.8)}.stat.blue .ico{color:var(--blue);background:rgba(219,237,255,.82)}.stat.gold .ico{color:var(--orange);background:rgba(255,243,213,.82)}.stat label{display:block;color:var(--muted);font-size:12px}.stat strong{font-size:25px;display:block;margin-top:2px}.twocol{display:grid;grid-template-columns:1.05fr 1fr;gap:14px}.card{padding:18px}.cardhead{display:flex;align-items:center;gap:9px;font-weight:800;font-size:16px;margin-bottom:14px}.cardhead .right{margin-left:auto;color:var(--muted);font-size:12px;font-weight:500}.dropgrid{display:grid;grid-template-columns:1.25fr .8fr;gap:12px}.dropzone{border:1px dashed rgba(116,143,183,.55);border-radius:15px;min-height:150px;display:flex;align-items:center;justify-content:center;text-align:center;color:var(--muted);background:rgba(255,255,255,.26);position:relative;transition:.2s}.dropzone.drag{border-color:var(--blue);background:rgba(225,240,255,.52)}.dropzone textarea{position:absolute;inset:0;width:100%;height:100%;resize:none;border:0;background:transparent;color:transparent;caret-color:var(--text);outline:0;padding:16px;opacity:.02}.dropzone .hint{pointer-events:none}.dropzone .hint b{color:#33445f;display:block;margin-bottom:5px}.preview{border:1px solid rgba(181,196,219,.5);background:rgba(255,255,255,.34);border-radius:14px;padding:12px;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;color:#526178;white-space:pre-wrap;overflow:auto;max-height:150px}.actions{display:flex;gap:10px;margin-top:11px}.btn{border:0;border-radius:12px;padding:11px 16px;font-weight:750;cursor:pointer}.btn.primary{background:linear-gradient(145deg,#1d324f,#0e1a2c);color:#fff;box-shadow:0 8px 20px rgba(20,36,61,.22),inset 0 1px 0 rgba(255,255,255,.18)}.btn.soft{border:1px solid rgba(174,190,215,.52);background:rgba(255,255,255,.48);color:#25344b}.formrow{display:grid;grid-template-columns:85px 1fr;align-items:center;gap:10px;margin-bottom:9px}.formrow label{font-size:12px;color:#526178;font-weight:700}.input,select{width:100%;height:38px;border:1px solid rgba(168,187,214,.5);border-radius:10px;background:rgba(255,255,255,.48);padding:0 11px;color:var(--text);outline:none}.switchrow{display:flex;align-items:center;gap:10px}.switch{width:46px;height:26px;border-radius:15px;background:#c8d2df;padding:3px;cursor:pointer;transition:.2s}.switch i{display:block;width:20px;height:20px;background:#fff;border-radius:50%;box-shadow:0 2px 7px rgba(0,0,0,.18);transition:.2s}.switch.on{background:#203b60}.switch.on i{transform:translateX(20px)}details.advanced{margin-top:12px;border-top:1px solid rgba(174,190,215,.35);padding-top:10px}details summary{cursor:pointer;color:#64748b;font-size:12px;font-weight:700}.modebar{display:flex;align-items:center;gap:12px;padding:13px 18px;margin-top:14px}.modebar .title{font-weight:800;margin-right:6px}.segments{display:flex;gap:8px}.seg{border:1px solid rgba(174,190,215,.5);background:rgba(255,255,255,.45);border-radius:999px;padding:9px 22px;cursor:pointer;font-weight:700;color:#384861}.seg.active{background:linear-gradient(145deg,#263f61,#101e32);color:#fff}.start{margin-left:auto;min-width:180px}.progresscard{display:flex;align-items:center;gap:16px;margin-top:10px;padding:12px 18px}.ring{width:34px;height:34px;border-radius:50%;border:5px solid #d7e5f7;border-top-color:var(--blue);animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}.progressmeta{width:270px}.progressmeta b{display:block}.progressmeta span{font-size:11px;color:var(--muted)}.track{height:10px;flex:1;background:rgba(194,210,232,.55);border-radius:999px;overflow:hidden}.track i{display:block;height:100%;width:0;background:linear-gradient(90deg,#1c9dff,#4d7dff);border-radius:999px;transition:.2s}.pct{width:48px;text-align:right;color:#536176}.results{margin-top:14px;padding:15px 18px 10px}.resulttop{display:flex;align-items:center;gap:9px}.resulttop b{font-size:16px}.chips{display:flex;gap:8px;margin-left:14px}.chip{border:1px solid transparent;border-radius:999px;padding:6px 13px;font-size:12px;cursor:pointer;background:rgba(255,255,255,.52)}.chip.active{background:#20344f;color:#fff}.chip.usable{color:#1677df;background:rgba(222,239,255,.7)}.chip.excellent{color:#0b9a69;background:rgba(220,250,238,.72)}.chip.edge{color:#d88600;background:rgba(255,243,216,.74)}.chip.failed{color:#d8334d;background:rgba(255,226,232,.72)}.tablewrap{overflow:auto;margin-top:11px;border-radius:14px;border:1px solid rgba(177,193,216,.38);background:rgba(255,255,255,.35)}table{border-collapse:collapse;width:100%;min-width:1050px}th,td{padding:10px 12px;border-bottom:1px solid rgba(185,199,219,.3);text-align:left;white-space:nowrap;font-size:12px}th{color:#66758b;background:rgba(238,244,251,.65);font-size:11px}tbody tr:hover{background:rgba(255,255,255,.48)}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px}.excellent .dot{background:var(--green)}.usable .dot{background:var(--blue)}.edge .dot{background:var(--orange)}.failed .dot{background:var(--red)}.footeractions{display:flex;justify-content:flex-end;gap:9px;margin-top:9px}.note{font-size:11px;color:var(--muted);margin-top:7px}.toast{position:fixed;right:28px;bottom:28px;max-width:420px;background:rgba(18,31,50,.91);color:#fff;padding:12px 16px;border-radius:12px;box-shadow:0 15px 45px rgba(0,0,0,.2);opacity:0;pointer-events:none;transform:translateY(10px);transition:.2s;z-index:30}.toast.show{opacity:1;transform:none}.hidden{display:none!important}@media(max-width:960px){body{padding:8px}.shell{width:100%}.main{padding:16px}.stats{grid-template-columns:repeat(2,1fr)}.twocol{grid-template-columns:1fr}.dropgrid{grid-template-columns:1fr}.topnav{display:none}.modebar{flex-wrap:wrap}.start{margin-left:0}.progressmeta{width:200px}}
</style>
</head>
<body>
<div class="shell">
  <div class="titlebar"><div class="lights"><i></i><i></i><i></i></div><div class="brandmark">⚡</div><div class="brand"><b>ProxyIP Optimizer</b><span>Local Network Benchmark</span></div><div class="topnav"><button class="ghost" id="settingsBtn">⚙ 设置</button><button class="ghost" id="aboutBtn">ⓘ 关于</button></div></div>
  <main class="main">
    <section class="hero"><h1>本地优选</h1><p>从 VPS 扫描器导入候选 ProxyIP，在当前电脑真实网络下按实际 SNI / TLS 行为进行验证；不再用固定公共域名一票淘汰。</p></section>
    <section class="stats">
      <div class="glass stat"><div class="ico">◉</div><div><label>总候选</label><strong id="statTotal">0</strong></div></div>
      <div class="glass stat green"><div class="ico">⌁</div><div><label>TCP 可达</label><strong id="statTCP">0</strong></div></div>
      <div class="glass stat blue"><div class="ico">✓</div><div><label>真实可用</label><strong id="statUsable">0</strong></div></div>
      <div class="glass stat gold"><div class="ico">♛</div><div><label>优质节点</label><strong id="statExcellent">0</strong></div></div>
    </section>
    <section class="twocol">
      <div class="glass card">
        <div class="cardhead">▤ 候选 IP <span class="right" id="importCount">已导入 0 条</span></div>
        <div class="dropgrid"><div class="dropzone" id="dropzone"><textarea id="candidates" spellcheck="false"></textarea><div class="hint"><b>⇧ 拖拽 TXT / CSV 文件到此处</b><span>或点击“粘贴导入”，支持 IP:端口 / IP 端口 / CSV</span></div></div><div class="preview" id="preview">等待导入候选…</div></div>
        <div class="actions"><button class="btn primary" id="importBtn">▣ 导入文件</button><button class="btn soft" id="pasteBtn">▢ 粘贴导入</button><input type="file" id="fileInput" accept=".txt,.csv,text/plain,text/csv" hidden></div>
      </div>
      <div class="glass card">
        <div class="cardhead">⚙ 实际使用配置 <button class="ghost right" id="saveDefaults">保存为默认配置</button></div>
        <div class="formrow"><label>SNI</label><input class="input" id="sni" autocomplete="off" placeholder="例如 example.com（建议填写实际使用域名）"></div>
        <div class="formrow"><label>Path</label><input class="input" id="path" value="/cdn-cgi/trace"></div>
        <div class="formrow"><label>TLS</label><div class="switchrow"><div class="switch on" id="tlsSwitch"><i></i></div><span id="tlsText">开启</span></div></div>
        <div class="note" id="sniNote">SNI 默认留空且不会写入仓库。留空时只做 TCP 本地筛选；Host 默认跟随 SNI。</div>
        <details class="advanced" id="advanced"><summary>高级设置</summary><div style="height:10px"></div>
          <div class="formrow"><label>Host</label><input class="input" id="host" placeholder="默认跟随 SNI"></div>
          <div class="formrow"><label>缺省端口</label><input class="input" id="fallbackPort" type="number" value="443" min="1" max="65535"></div>
          <div class="formrow"><label>并发</label><input class="input" id="threads" type="number" value="30" min="1" max="100"></div>
          <div class="formrow"><label>单次超时</label><input class="input" id="timeoutMs" type="number" value="5000" min="1500" max="15000"></div>
          <div class="formrow"><label>忽略证书</label><div class="switchrow"><div class="switch" id="insecureSwitch"><i></i></div><span id="insecureText">关闭</span></div></div>
          <div class="note">“忽略证书”只用于你在 v2rayN 中确实开启 allowInsecure 的情况；默认关闭更接近正常 TLS 配置。</div>
        </details>
      </div>
    </section>
    <section class="glass modebar"><div class="title">◎ 优选模式</div><div class="segments"><button class="seg" data-mode="fast">⚡ 极速</button><button class="seg active" data-mode="standard">☷ 标准</button><button class="seg" data-mode="precise">◉ 精准</button></div><button class="btn primary start" id="startBtn">▶ 开始优选</button><button class="btn soft hidden" id="stopBtn">■ 停止</button></section>
    <section class="glass progresscard"><div class="ring" id="ring"></div><div class="progressmeta"><b id="progressTitle">等待开始</b><span id="progressSub">本地链路验证</span></div><div class="track"><i id="progressBar"></i></div><div class="pct" id="progressPct">0%</div></section>
    <section class="glass results"><div class="resulttop"><b>☷ 结果</b><div class="chips"><button class="chip active" data-filter="all">全部 <span id="chipAll">0</span></button><button class="chip usable" data-filter="usable">可用 <span id="chipUsable">0</span></button><button class="chip excellent" data-filter="excellent">优质 <span id="chipExcellent">0</span></button><button class="chip edge" data-filter="edge">边缘 <span id="chipEdge">0</span></button><button class="chip failed" data-filter="failed">失败 <span id="chipFailed">0</span></button></div></div>
      <div class="tablewrap"><table><thead><tr><th>IP:端口</th><th>状态</th><th>成功率</th><th>TCP</th><th>TLS</th><th>TTFB</th><th>CF</th><th>机房</th><th>速度</th><th>评分</th><th>说明</th></tr></thead><tbody id="tbody"><tr><td colspan="11" style="text-align:center;color:#8390a3;padding:32px">导入候选后开始优选</td></tr></tbody></table></div>
      <div class="footeractions"><button class="btn soft" id="copyTop">▢ 复制 Top10</button><button class="btn soft" id="exportTxt">▤ 导出 TXT</button><button class="btn soft" id="exportCsv">▦ 导出 CSV</button></div>
    </section>
  </main>
</div><div class="toast" id="toast"></div>
<script>
const $=id=>document.getElementById(id);let socket=null,mode='standard',tls=true,insecure=false,running=false,results=[],filter='all',fileName='manual.txt';
function toast(msg){const el=$('toast');el.textContent=msg;el.classList.add('show');clearTimeout(toast.t);toast.t=setTimeout(()=>el.classList.remove('show'),2600)}
function connect(){const proto=location.protocol==='https:'?'wss:':'ws:';socket=new WebSocket(proto+'//'+location.host+'/ws');socket.onopen=()=>toast('本地引擎已连接');socket.onclose=()=>{if(running)toast('本地引擎连接已断开');setTimeout(connect,1800)};socket.onmessage=e=>{let m;try{m=JSON.parse(e.data)}catch{return}handleMessage(m.type,m.data)}}
function send(type,data={}){if(!socket||socket.readyState!==1){toast('本地引擎尚未连接');return false}socket.send(JSON.stringify({type,data}));return true}
function handleMessage(type,data){if(type==='error'){toast(typeof data==='string'?data:'任务错误');finishRun();return}if(type==='proxy_started'){results=[];updateSummary({total:data.total,tcpReachable:0,realUsable:0,excellent:0,usable:0,edge:0,failed:0});render();return}if(type==='proxy_result'){upsert(data);render();return}if(type==='proxy_progress'){const total=Number(data.total||0),cur=Number(data.current||0),pct=total?Math.round(cur/total*100):0;$('progressTitle').textContent=data.text||'本地优选中';$('progressSub').textContent=cur+' / '+total;$('progressBar').style.width=pct+'%';$('progressPct').textContent=pct+'%';return}if(type==='proxy_complete'){results=Array.isArray(data.results)?data.results:results;sortResults();updateSummary(data.summary||summaryFromResults());render();finishRun();$('progressTitle').textContent=data.partial?'已停止，保留当前结果':'优选完成';$('progressSub').textContent='共 '+results.length+' 条结果';$('progressBar').style.width='100%';$('progressPct').textContent='100%';return}if(type==='log'&&typeof data==='string')console.log('[engine]',data)}
function finishRun(){running=false;$('startBtn').classList.remove('hidden');$('stopBtn').classList.add('hidden')}
function upsert(row){const k=row.endpoint||row.ip+':'+row.port,i=results.findIndex(x=>(x.endpoint||x.ip+':'+x.port)===k);if(i>=0)results[i]=row;else results.push(row);sortResults();updateSummary(summaryFromResults())}
function rank(s){return s==='excellent'?0:s==='usable'?1:s==='edge'?2:3}function sortResults(){results.sort((a,b)=>rank(a.status)-rank(b.status)||(Number(b.score||0)-Number(a.score||0))||(Number(b.speedMbps||0)-Number(a.speedMbps||0)))}
function summaryFromResults(){const s={total:results.length,tcpReachable:0,realUsable:0,excellent:0,usable:0,edge:0,failed:0};for(const r of results){if(Number(r.tcpSuccesses)>0)s.tcpReachable++;if(r.status==='excellent'){s.excellent++;s.realUsable++}else if(r.status==='usable'){s.usable++;s.realUsable++}else if(r.status==='edge')s.edge++;else s.failed++}return s}
function updateSummary(s){$('statTotal').textContent=s.total||0;$('statTCP').textContent=s.tcpReachable||0;$('statUsable').textContent=s.realUsable||0;$('statExcellent').textContent=s.excellent||0;$('chipAll').textContent=s.total||0;$('chipUsable').textContent=(s.realUsable||0);$('chipExcellent').textContent=s.excellent||0;$('chipEdge').textContent=s.edge||0;$('chipFailed').textContent=s.failed||0}
const statusText={excellent:'优质',usable:'可用',edge:'边缘',failed:'失败'};function ms(v){return Number(v)>0?Number(v)+'ms':'--'}
function visibleRows(){if(filter==='all')return results;if(filter==='usable')return results.filter(r=>r.status==='excellent'||r.status==='usable');return results.filter(r=>r.status===filter)}
function render(){const rows=visibleRows();if(!rows.length){$('tbody').innerHTML='<tr><td colspan="11" style="text-align:center;color:#8390a3;padding:30px">当前筛选暂无结果</td></tr>';return}$('tbody').innerHTML=rows.map(r=>'<tr class="'+r.status+'"><td>'+esc(r.endpoint||r.ip+':'+r.port)+'</td><td><span class="dot"></span>'+statusText[r.status]+'</td><td>'+Number(r.successRate||0)+'%</td><td>'+ms(r.tcpMs)+'</td><td>'+ms(r.tlsMs)+'</td><td>'+ms(r.ttfbMs)+'</td><td>'+(r.cfConfirmed?'✓':'--')+'</td><td>'+esc(r.colo||r.loc||'--')+'</td><td>'+(Number(r.speedMbps)>0?Number(r.speedMbps).toFixed(1)+'Mbps':'--')+'</td><td>'+Number(r.score||0).toFixed(1)+'</td><td title="'+esc(r.error||'')+'">'+esc((r.error||'').slice(0,46)||'--')+'</td></tr>').join('')}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function parseLocalCount(text){return text.split(/\r?\n/).map(x=>x.trim()).filter(x=>x&&!x.startsWith('#')).length}function refreshImport(){const text=$('candidates').value,count=parseLocalCount(text);$('importCount').textContent='已导入 '+count+' 条';$('preview').textContent=text.trim()?text.split(/\r?\n/).slice(0,10).join('\n')+(count>10?'\n…':''):'等待导入候选…'}
async function readFile(file){fileName=file.name;const text=await file.text();$('candidates').value=text;refreshImport();toast('已导入 '+file.name)}
$('importBtn').onclick=()=>$('fileInput').click();$('fileInput').onchange=e=>{if(e.target.files[0])readFile(e.target.files[0])};$('pasteBtn').onclick=async()=>{try{const t=await navigator.clipboard.readText();if(t){$('candidates').value=t;fileName='clipboard.txt';refreshImport();toast('已从剪贴板导入')}}catch{toast('浏览器未授权读取剪贴板，可直接点击导入区域粘贴')}};$('candidates').oninput=refreshImport;
const dz=$('dropzone');['dragenter','dragover'].forEach(n=>dz.addEventListener(n,e=>{e.preventDefault();dz.classList.add('drag')}));['dragleave','drop'].forEach(n=>dz.addEventListener(n,e=>{e.preventDefault();dz.classList.remove('drag')}));dz.addEventListener('drop',e=>{if(e.dataTransfer.files[0])readFile(e.dataTransfer.files[0])});
function toggleSwitch(el,on,textEl){el.classList.toggle('on',on);$(textEl).textContent=on?'开启':'关闭'}$('tlsSwitch').onclick=()=>{tls=!tls;toggleSwitch($('tlsSwitch'),tls,'tlsText')};$('insecureSwitch').onclick=()=>{insecure=!insecure;toggleSwitch($('insecureSwitch'),insecure,'insecureText')};
document.querySelectorAll('.seg').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;document.querySelectorAll('.seg').forEach(x=>x.classList.toggle('active',x===b));if(mode==='fast'){$('threads').value=50;$('timeoutMs').value=3500}else if(mode==='precise'){$('threads').value=20;$('timeoutMs').value=6500}else{$('threads').value=30;$('timeoutMs').value=5000}});
$('startBtn').onclick=()=>{const text=$('candidates').value.trim();if(!text){toast('先导入候选 IP');return}const sni=$('sni').value.trim();if(tls&&!sni)toast('SNI 为空：本轮仅做 TCP 本地筛选');results=[];render();running=true;$('startBtn').classList.add('hidden');$('stopBtn').classList.remove('hidden');$('progressTitle').textContent='准备开始';$('progressSub').textContent='本地链路验证';send('start_proxy_task',{fileName,fileContent:text,fallbackPort:Number($('fallbackPort').value||443),sni,host:$('host').value.trim(),path:$('path').value.trim()||'/cdn-cgi/trace',enableTLS:tls,mode,threads:Number($('threads').value||0),timeoutMs:Number($('timeoutMs').value||0),insecure,speedLimit:mode==='precise'?10:0})};$('stopBtn').onclick=()=>{send('stop_task');$('progressTitle').textContent='正在停止…'};
document.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{filter=c.dataset.filter;document.querySelectorAll('.chip').forEach(x=>x.classList.toggle('active',x===c));render()});
function usableResults(){return results.filter(r=>r.status==='excellent'||r.status==='usable')}function download(name,text,type='text/plain'){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500)}$('copyTop').onclick=async()=>{const text=usableResults().slice(0,10).map(r=>r.endpoint).join('\n');if(!text){toast('暂无可复制的可用结果');return}await navigator.clipboard.writeText(text);toast('已复制 Top10')};$('exportTxt').onclick=()=>{const rows=usableResults();if(!rows.length){toast('暂无可导出的可用结果');return}download('proxyip-best.txt',rows.map(r=>r.endpoint).join('\n')+'\n')};$('exportCsv').onclick=()=>{const rows=results;if(!rows.length){toast('暂无结果');return}const h=['endpoint','status','successRate','tcpMs','tlsMs','ttfbMs','cfConfirmed','colo','loc','exitIp','speedMbps','score','error'];const csv=[h.join(','),...rows.map(r=>h.map(k=>'"'+String(r[k]??'').replaceAll('"','""')+'"').join(','))].join('\r\n');download('proxyip-results.csv','\ufeff'+csv,'text/csv')};
$('saveDefaults').onclick=()=>{localStorage.setItem('proxyipOptimizerConfig',JSON.stringify({sni:$('sni').value,path:$('path').value,host:$('host').value,fallbackPort:$('fallbackPort').value,threads:$('threads').value,timeoutMs:$('timeoutMs').value,tls,insecure,mode}));toast('配置仅保存在当前浏览器本地')};function loadDefaults(){try{const c=JSON.parse(localStorage.getItem('proxyipOptimizerConfig')||'{}');if(c.sni)$('sni').value=c.sni;if(c.path)$('path').value=c.path;if(c.host)$('host').value=c.host;if(c.fallbackPort)$('fallbackPort').value=c.fallbackPort;if(c.threads)$('threads').value=c.threads;if(c.timeoutMs)$('timeoutMs').value=c.timeoutMs;if(typeof c.tls==='boolean'){tls=c.tls;toggleSwitch($('tlsSwitch'),tls,'tlsText')}if(typeof c.insecure==='boolean'){insecure=c.insecure;toggleSwitch($('insecureSwitch'),insecure,'insecureText')}if(c.mode){mode=c.mode;document.querySelectorAll('.seg').forEach(x=>x.classList.toggle('active',x.dataset.mode===mode))}}catch{}}
$('settingsBtn').onclick=()=>{$('advanced').open=!$('advanced').open;$('advanced').scrollIntoView({behavior:'smooth',block:'center'})};$('aboutBtn').onclick=()=>toast('ProxyIP Optimizer · 本地优选引擎 · GPL-3.0-or-later');loadDefaults();refreshImport();connect();
</script>
</body></html>
'''

readme = r'''# ProxyIP Optimizer

一个轻量的 **本地 ProxyIP 优选工具**，核心使用 Go，本地 Web UI 使用原生 HTML / CSS / JavaScript，不依赖 Electron。

## 当前目标

VPS 端负责大规模海选 ProxyIP；本工具负责在你的 Windows / macOS / Linux **当前真实网络**下进行最终优选。

与传统 CF 优选判定不同，本项目的 ProxyIP 模式遵循：

- 不使用固定 `speed.cloudflare.com` 作为“是否可用”的唯一标准。
- SNI 默认留空；建议填入你实际使用的 SNI。
- Host 默认跟随 SNI，仅在高级设置中允许单独覆盖。
- TCP / TLS / HTTP 多次复检，单次失败不会直接淘汰。
- HTTP 4xx / 5xx 只要真实 TLS + HTTP 链路建立成功，仍作为链路证据记录，不直接判死。
- `/cdn-cgi/trace` 没有 `colo` 不再一票否决。
- 失败节点分为“边缘”和“失败”，尽量减少实际可用节点被误杀。
- 精准模式的公共测速仅用于参考；测速失败不会改变真实可用判定。

## 使用流程

1. 从 VPS ProxyIP Scanner 导出候选 `IP:端口`。
2. 在本机运行 ProxyIP Optimizer。
3. 导入 TXT / CSV，填写实际 SNI。
4. 选择 极速 / 标准 / 精准。
5. 根据成功率、TCP、TLS、TTFB、CF 确认、参考速度和评分挑选 Top 节点。

SNI、Host 等个人配置只保存在浏览器 `localStorage`，源码默认值不包含任何个人域名。

## 构建

正式后端位于 `combined_refactor/`：

```bash
cd combined_refactor
go build -trimpath -ldflags "-s -w" -o proxyip-optimizer .
```

Windows：

```bash
cd combined_refactor
set GOOS=windows
set GOARCH=amd64
go build -trimpath -ldflags "-s -w" -o proxyip-optimizer.exe .
```

默认本地 Web 地址沿用后端监听端口 `13335`。

## License / Attribution

本项目基于 CFData-WEB 继续开发，并保留原项目 GPL-3.0-or-later 授权要求与版权信息。修改版继续采用 GNU General Public License v3.0 or later；详见 `LICENSE`。

在当前私有开发阶段仅用于内部测试。若未来公开或分发二进制版本，将按 GPL-3.0-or-later 要求同步提供对应源码与许可信息。
'''

# New source files.
(GO_DIR / 'proxy_local.go').write_text(proxy_go, encoding='utf-8')
(GO_DIR / 'proxy_local_test.go').write_text(proxy_test, encoding='utf-8')
(GO_DIR / 'index.html').write_text(index_html, encoding='utf-8')
(ROOT / 'README.md').write_text(readme, encoding='utf-8')

# Add the dedicated websocket entry without disturbing legacy NSB/official paths.
server = (GO_DIR / 'server.go').read_text(encoding='utf-8')
needle = '\t\t"start_nsb_task": func(data json.RawMessage) {'
if '"start_proxy_task"' not in server:
    block = r'''\t\t"start_proxy_task": func(data json.RawMessage) {
\t\t\tvar params proxyLocalTaskRequest
\t\t\tif err := json.Unmarshal(data, &params); err != nil {
\t\t\t\tsession.sendWSMessage("error", "start_proxy_task 参数解析失败")
\t\t\t\treturn
\t\t\t}
\t\t\tif strings.TrimSpace(params.FileContent) == "" {
\t\t\t\tsession.sendWSMessage("error", "请先导入候选 IP")
\t\t\t\treturn
\t\t\t}
\t\t\tsession.startTaskNamed("ProxyIP 本地优选", "proxy", map[string]interface{}{
\t\t\t\t"fileName": params.FileName, "sniConfigured": strings.TrimSpace(params.SNI) != "",
\t\t\t\t"mode": params.Mode, "threads": params.Threads,
\t\t\t}, func(ctx context.Context, session *appSession) {
\t\t\t\trunProxyLocalTask(ctx, session, params)
\t\t\t})
\t\t},
'''.replace('\\t', '\t')
    if needle not in server:
        raise SystemExit('server insertion point not found')
    server = server.replace(needle, block + needle, 1)
(GO_DIR / 'server.go').write_text(server, encoding='utf-8')

# Rebrand executable-facing update URLs / user-agent strings, while leaving LICENSE intact.
for path in GO_DIR.glob('*.go'):
    text = path.read_text(encoding='utf-8')
    text = text.replace('https://api.github.com/repos/PoemMisty/CFData-WEB/releases/latest', 'https://api.github.com/repos/jasonrong0130/cf-proxyipscan/releases/latest')
    text = text.replace('https://github.com/PoemMisty/CFData-WEB/releases/latest', 'https://github.com/jasonrong0130/cf-proxyipscan/releases/latest')
    text = text.replace('CFData-WEB', 'ProxyIP Optimizer')
    path.write_text(text, encoding='utf-8')

workflow = ROOT / '.github/workflows/build.yml'
if workflow.exists():
    text = workflow.read_text(encoding='utf-8')
    text = text.replace('filename="cfdata-', 'filename="proxyip-optimizer-')
    text = text.replace('release_assets/cfdata-', 'release_assets/proxyip-optimizer-')
    text = text.replace('cfdata-android-arm64.apk', 'proxyip-optimizer-android-arm64.apk')
    text = text.replace('CFData-WEB Release', 'ProxyIP Optimizer')
    workflow.write_text(text, encoding='utf-8')

print('ProxyIP Local V1 source migration applied')
