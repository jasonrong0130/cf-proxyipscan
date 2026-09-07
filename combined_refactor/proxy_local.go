package main

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
	SNI        string
	Host       string
	Path       string
	EnableTLS  bool
	Insecure   bool
	Attempts   int
	Threads    int
	Timeout    time.Duration
	Mode       string
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
	IP            string  `json:"ip"`
	Port          int     `json:"port"`
	Endpoint      string  `json:"endpoint"`
	Status        string  `json:"status"`
	SuccessRate   int     `json:"successRate"`
	Attempts      int     `json:"attempts"`
	TCPSuccesses  int     `json:"tcpSuccesses"`
	TLSSuccesses  int     `json:"tlsSuccesses"`
	HTTPSuccesses int     `json:"httpSuccesses"`
	TCPMS         int64   `json:"tcpMs"`
	TLSMS         int64   `json:"tlsMs"`
	TTFBMS        int64   `json:"ttfbMs"`
	HTTPStatus    int     `json:"httpStatus"`
	CFConfirmed   bool    `json:"cfConfirmed"`
	Colo          string  `json:"colo,omitempty"`
	Loc           string  `json:"loc,omitempty"`
	ExitIP        string  `json:"exitIp,omitempty"`
	Score         float64 `json:"score"`
	SpeedMbps     float64 `json:"speedMbps,omitempty"`
	Error         string  `json:"error,omitempty"`
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
		SNI:        sni,
		Host:       host,
		Path:       normalizeProxyPath(req.Path),
		EnableTLS:  req.EnableTLS,
		Insecure:   req.Insecure,
		Attempts:   attempts,
		Threads:    threads,
		Timeout:    time.Duration(timeoutMS) * time.Millisecond,
		Mode:       mode,
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
		IP:       candidate.Host,
		Port:     candidate.Port,
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
