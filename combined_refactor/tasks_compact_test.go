package main

import "testing"

func TestCompactScanUsesEDTTLSports(t *testing.T) {
	want := []int{443, 2053, 2083, 2087, 2096, 8443}
	if len(compactIPv4Ports) != len(want) {
		t.Fatalf("compact ports = %v, want %v", compactIPv4Ports, want)
	}
	for i := range want {
		if compactIPv4Ports[i] != want[i] {
			t.Fatalf("compact ports = %v, want %v", compactIPv4Ports, want)
		}
	}
}
