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
	cfg := normalizeProxyConfig(proxyLocalTaskRequest{EnableTLS: true})
	if cfg.SNI != "" || cfg.Host != "" {
		t.Fatalf("SNI/Host must remain blank by default: %#v", cfg)
	}
	if cfg.Path != "/cdn-cgi/trace" || cfg.Attempts != 1 || cfg.Threads != 8 {
		t.Fatalf("unexpected lightweight defaults: %#v", cfg)
	}
}

func TestNormalizeProxyConfigAllowsManualAttempts(t *testing.T) {
	cfg := normalizeProxyConfig(proxyLocalTaskRequest{Attempts: 3, Threads: 60, TimeoutMS: 7000})
	if cfg.Attempts != 3 || cfg.Threads != 16 || cfg.Timeout != 7000000000 {
		t.Fatalf("manual test config not preserved: %#v", cfg)
	}
}

func TestClassifyRequiresHTTPForEligible(t *testing.T) {
	cfg := proxyProbeConfig{SNI: "example.com", Host: "example.com", EnableTLS: true}
	result := proxyLocalResult{Attempts: 1, TCPSuccesses: 1, TLSSuccesses: 1, HTTPSuccesses: 0, TCPMS: 35}
	classifyProxyResult(&result, cfg, 0)
	if result.Status != "failed" || result.Stage != "tls" || result.SuccessRate != 0 {
		t.Fatalf("TLS-only candidate must not be marked eligible, got %#v", result)
	}
}

func TestClassifyHTTPResponse(t *testing.T) {
	cfg := proxyProbeConfig{SNI: "example.com", Host: "example.com", EnableTLS: true}
	result := proxyLocalResult{Attempts: 1, TCPSuccesses: 1, TLSSuccesses: 1, HTTPSuccesses: 1, TTFBMS: 110}
	classifyProxyResult(&result, cfg, 1)
	if result.Status != "success" || result.Stage != "http" || result.SuccessRate != 100 {
		t.Fatalf("expected factual HTTP result, got %#v", result)
	}
}
