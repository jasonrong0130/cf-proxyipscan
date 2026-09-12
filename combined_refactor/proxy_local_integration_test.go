package main

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
	got, err := parseProxyCandidates(input, 443, nil)
	if err != nil {
		t.Fatalf("parse failed: %v", err)
	}
	if len(got) != 5 {
		t.Fatalf("expected 5 unique candidates, got %d: %#v", len(got), got)
	}
	if got[1].Host != "5.6.7.8" || got[1].Port != 443 || got[3].Port != 8443 {
		t.Fatalf("multi-port parsing changed: %#v", got)
	}
}

func TestTCPOnlyIsNotEligible(t *testing.T) {
	cfg := normalizeProxyConfig(proxyLocalTaskRequest{EnableTLS: true, SNI: "example.com"})
	r := proxyLocalResult{Attempts: cfg.Attempts, TCPSuccesses: 1, TCPMS: 40}
	classifyProxyResult(&r, cfg, 0)
	if r.Status != "failed" || r.Stage != "tcp" || r.SuccessRate != 0 {
		t.Fatalf("TCP-only candidate must not be marked eligible, got %#v", r)
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
		t.Fatalf("403 Cloudflare response should remain factual evidence: %#v", attempt)
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

func TestProxyLocalUIHasSafeDefaults(t *testing.T) {
	data, err := staticFiles.ReadFile("index.html")
	if err != nil {
		t.Fatal(err)
	}
	html := string(data)
	required := []string{"CF优选IP筛选器", "start_proxy_task", "example.com", "Host 默认跟随 SNI", "一键测速", "停止测速", "请先填写实际使用的 SNI", "pageSize", "filterSpeed", "exportModal", "归属地", "当前筛选结果"}
	for _, item := range required {
		if !strings.Contains(html, item) {
			t.Fatalf("UI missing required marker %q", item)
		}
	}
	if strings.Contains(html, "value=\"example.com\"") {
		t.Fatal("SNI example must remain a placeholder, not a persisted default value")
	}
	if !strings.Contains(html, "id=\"threads\" type=\"number\" value=\"8\" min=\"1\" max=\"512\"") || !strings.Contains(html, "id=\"speedThreads\" type=\"number\" value=\"1\" min=\"1\" max=\"16\"") {
		t.Fatal("V4 safe defaults / configurable concurrency are missing")
	}
	if strings.Contains(html, "data-sort=\"httpStatus\">HTTP") || strings.Contains(html, "<th>说明</th>") {
		t.Fatal("HTTP/说明 columns must remain removed from the V4 result table")
	}
}
