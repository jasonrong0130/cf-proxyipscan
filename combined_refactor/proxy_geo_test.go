package main

import "testing"

func TestProxyCountryLabel(t *testing.T) {
	if got := proxyCountryLabel("HK"); got != "香港（HK）" {
		t.Fatalf("unexpected HK label: %q", got)
	}
	if got := proxyCountryLabel("US"); got != "美国（US）" {
		t.Fatalf("unexpected US label: %q", got)
	}
}

func TestProxyGeoLabelPrefersCountryCity(t *testing.T) {
	got := proxyGeoLabel(proxyGeoPayload{Success: true, CountryCode: "JP", Country: "Japan", City: "Tokyo"})
	if got != "日本 · Tokyo" {
		t.Fatalf("unexpected geo label: %q", got)
	}
}
