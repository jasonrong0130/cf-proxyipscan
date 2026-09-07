package main

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
