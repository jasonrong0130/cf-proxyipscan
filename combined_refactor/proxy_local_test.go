package main

import "testing"

func TestParseProxyCandidates(t *testing.T) {
	input := "IP,Port\n1.2.3.4,443\n5.6.7.8:8443\n1.1.1.1\n9.9.9.9:443,2053\n"
	rows, err := parseProxyCandidates(input, 443, nil)
	if err != nil {
		t.Fatalf("parse failed: %v", err)
	}
	if len(rows) != 10 {
		t.Fatalf("expected 10 candidates with all default EDT ports, got %d: %#v", len(rows), rows)
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
	if cfg.Attempts != 3 || cfg.Threads != 60 || cfg.Timeout != 7000000000 {
		t.Fatalf("manual test config not preserved: %#v", cfg)
	}
}

func TestNormalizeProxyConfigCapsExtremeConcurrency(t *testing.T) {
	cfg := normalizeProxyConfig(proxyLocalTaskRequest{Threads: 9999})
	if cfg.Threads != 512 {
		t.Fatalf("extreme concurrency must be capped at 512, got %d", cfg.Threads)
	}
}

func TestClassifyAcceptsTLSWithoutTraceHTTP(t *testing.T) {
	cfg := proxyProbeConfig{SNI: "example.com", Host: "example.com", EnableTLS: true}
	result := proxyLocalResult{Attempts: 1, TCPSuccesses: 1, TLSSuccesses: 1, HTTPSuccesses: 0, TCPMS: 35}
	classifyProxyResult(&result, cfg, 0)
	if result.Status != "success" || result.Stage != "tls" || result.SuccessRate != 100 {
		t.Fatalf("TLS-reachable candidate must remain eligible when trace/HTTP enrichment fails, got %#v", result)
	}
}

func TestDefaultEDTScanPorts(t *testing.T) {
	want := []int{443, 2053, 2083, 2087, 2096, 8443}
	got := normalizeProxyPorts(nil, 443)
	if len(got) != len(want) {
		t.Fatalf("default EDT ports = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("default EDT ports = %v, want %v", got, want)
		}
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

func TestParseProxyCIDRMultiPort(t *testing.T) {
	rows, err := parseProxyCandidates("192.0.2.0/30\n", 443, []int{443, 2053, 8443})
	if err != nil {
		t.Fatalf("parse failed: %v", err)
	}
	if len(rows) != 12 {
		t.Fatalf("expected 12 expanded candidates, got %d", len(rows))
	}
	if rows[0].Host != "192.0.2.0" || rows[0].Port != 443 {
		t.Fatalf("unexpected first candidate: %#v", rows[0])
	}
	if rows[11].Host != "192.0.2.3" || rows[11].Port != 8443 {
		t.Fatalf("unexpected last candidate: %#v", rows[11])
	}
}

func TestParseProxyRangeMultiPort(t *testing.T) {
	rows, err := parseProxyCandidates("198.51.100.10-198.51.100.12\n", 443, []int{443, 2096})
	if err != nil {
		t.Fatalf("parse failed: %v", err)
	}
	if len(rows) != 6 {
		t.Fatalf("expected 6 expanded candidates, got %d", len(rows))
	}
}

func TestExplicitPortOverridesSelectedPorts(t *testing.T) {
	rows, err := parseProxyCandidates("203.0.113.8:8443\n", 443, []int{443, 2053})
	if err != nil {
		t.Fatalf("parse failed: %v", err)
	}
	if len(rows) != 1 || rows[0].Port != 8443 {
		t.Fatalf("explicit port must override selected ports: %#v", rows)
	}
}
