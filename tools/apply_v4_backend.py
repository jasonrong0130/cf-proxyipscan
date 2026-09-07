from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]

def replace_once(path, old, new):
    p=ROOT/path
    s=p.read_text(encoding='utf-8')
    if old not in s:
        raise SystemExit(f'marker not found in {path}: {old[:120]!r}')
    p.write_text(s.replace(old,new,1),encoding='utf-8')

# Local probe: lower default/cap and add location fields/enrichment.
replace_once('combined_refactor/proxy_local.go',
'''\tEntryASN      string `json:"entryAsn,omitempty"`
\tEntryOrg      string `json:"entryOrg,omitempty"`
\tExitASN       string `json:"exitAsn,omitempty"`
\tExitOrg       string `json:"exitOrg,omitempty"`
\tError         string `json:"error,omitempty"`''',
'''\tEntryASN       string `json:"entryAsn,omitempty"`
\tEntryOrg       string `json:"entryOrg,omitempty"`
\tExitASN        string `json:"exitAsn,omitempty"`
\tExitOrg        string `json:"exitOrg,omitempty"`
\tLocation       string `json:"location,omitempty"`
\tLocationSource string `json:"locationSource,omitempty"`
\tError          string `json:"error,omitempty"`''')
replace_once('combined_refactor/proxy_local.go',
             '\tthreads := clampProxyInt(req.Threads, 30, 1, 100)',
             '\tthreads := clampProxyInt(req.Threads, 8, 1, 16)')
replace_once('combined_refactor/proxy_local.go',
'''\tclassifyProxyResult(&result, cfg, strongSuccesses)
\treturn result''',
'''\tclassifyProxyResult(&result, cfg, strongSuccesses)
\tenrichProxyLocation(ctx, &result)
\treturn result''')

# Lightweight exit-first GeoIP fallback. Trace loc is free; external lookup only when eligible + trace loc absent.
(ROOT/'combined_refactor/proxy_geo.go').write_text(r'''package main

import (
    "context"
    "encoding/json"
    "io"
    "net"
    "net/http"
    "net/url"
    "strings"
    "sync"
    "time"
)

type proxyGeoPayload struct {
    Success     bool   `json:"success"`
    CountryCode string `json:"country_code"`
    Country     string `json:"country"`
    Region      string `json:"region"`
    City        string `json:"city"`
}

var proxyGeoCache sync.Map
var proxyGeoSem = make(chan struct{}, 2)
var proxyGeoClient = &http.Client{
    Timeout: 4 * time.Second,
    Transport: &http.Transport{
        MaxIdleConns:        4,
        MaxIdleConnsPerHost: 2,
        IdleConnTimeout:     30 * time.Second,
        DisableCompression:  true,
    },
}

var proxyCountryZH = map[string]string{
    "HK": "香港", "MO": "澳门", "TW": "台湾", "CN": "中国大陆",
    "JP": "日本", "KR": "韩国", "SG": "新加坡", "US": "美国",
    "DE": "德国", "IE": "爱尔兰", "GB": "英国", "FR": "法国",
    "NL": "荷兰", "CA": "加拿大", "AU": "澳大利亚", "CL": "智利",
    "BR": "巴西", "IN": "印度", "ID": "印度尼西亚", "MY": "马来西亚",
    "TH": "泰国", "VN": "越南", "PH": "菲律宾", "RU": "俄罗斯",
    "SE": "瑞典", "FI": "芬兰", "NO": "挪威", "DK": "丹麦",
    "CH": "瑞士", "AT": "奥地利", "IT": "意大利", "ES": "西班牙",
    "PL": "波兰", "CZ": "捷克", "RO": "罗马尼亚", "TR": "土耳其",
    "AE": "阿联酋", "ZA": "南非", "MX": "墨西哥", "AR": "阿根廷",
}

func proxyCountryLabel(code string) string {
    code = strings.ToUpper(strings.TrimSpace(code))
    if code == "" { return "" }
    if name := proxyCountryZH[code]; name != "" { return name + "（" + code + "）" }
    return code
}

func proxyGeoLabel(data proxyGeoPayload) string {
    code := strings.ToUpper(strings.TrimSpace(data.CountryCode))
    country := proxyCountryZH[code]
    if country == "" { country = strings.TrimSpace(data.Country) }
    if country == "" { country = code }
    city := strings.TrimSpace(data.City)
    if city == "" { city = strings.TrimSpace(data.Region) }
    if country == "" { return city }
    if city != "" && !strings.EqualFold(city, country) { return country + " · " + city }
    if code != "" && country != code { return country + "（" + code + "）" }
    return country
}

func lookupProxyGeo(ctx context.Context, ip string) string {
    ip = strings.TrimSpace(ip)
    parsed := net.ParseIP(ip)
    if parsed == nil || parsed.IsLoopback() || parsed.IsPrivate() || parsed.IsUnspecified() { return "" }
    if cached, ok := proxyGeoCache.Load(ip); ok { return cached.(string) }
    select {
    case proxyGeoSem <- struct{}{}:
        defer func(){ <-proxyGeoSem }()
    case <-ctx.Done():
        return ""
    }
    if cached, ok := proxyGeoCache.Load(ip); ok { return cached.(string) }
    req, err := http.NewRequestWithContext(ctx, http.MethodGet, "https://ipwho.is/"+url.PathEscape(ip), nil)
    if err != nil { return "" }
    req.Header.Set("User-Agent", "CF-IP-Selector/1.0")
    resp, err := proxyGeoClient.Do(req)
    if err != nil { return "" }
    defer resp.Body.Close()
    if resp.StatusCode < 200 || resp.StatusCode >= 300 { return "" }
    raw, err := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
    if err != nil { return "" }
    var data proxyGeoPayload
    if json.Unmarshal(raw, &data) != nil || !data.Success { return "" }
    label := proxyGeoLabel(data)
    if label != "" { proxyGeoCache.Store(ip, label) }
    return label
}

func enrichProxyLocation(ctx context.Context, result *proxyLocalResult) {
    if result == nil { return }
    if code := strings.TrimSpace(result.Loc); code != "" {
        result.Location = proxyCountryLabel(code)
        result.LocationSource = "出口"
        return
    }
    if result.Status != "success" { return }
    if result.ExitIP != "" {
        if label := lookupProxyGeo(ctx, result.ExitIP); label != "" {
            result.Location = label
            result.LocationSource = "出口"
            return
        }
    }
    if label := lookupProxyGeo(ctx, result.IP); label != "" {
        result.Location = label
        result.LocationSource = "入口（出口未知）"
    }
}
''', encoding='utf-8')

# Speed test: bounded transfer, large buffer, no per-chunk goroutine/channel.
p=ROOT/'combined_refactor/tasks_nsb.go'
s=p.read_text(encoding='utf-8')
pattern=r'func runNSBDownloadSpeed\(ctx context\.Context, ip string, port int, enableTLS bool, testURL string\) \(float64, string\) \{.*?\n\}\n\nfunc runNSBTask'
new=r'''func runNSBDownloadSpeed(ctx context.Context, ip string, port int, enableTLS bool, testURL string) (float64, string) {
\tconst speedWindow = 5 * time.Second
\tconst speedMaxBytes int64 = 32 * 1024 * 1024
\tconst speedBufferSize = 256 * 1024

\tscheme := "http"
\tif enableTLS { scheme = "https" }
\tparsedURL, err := parseSpeedTestURL(testURL, scheme)
\tif err != nil { return 0, "测速地址解析失败: " + err.Error() }

\ttransport := &http.Transport{
\t\tDialContext: func(c context.Context, network, addr string) (net.Conn, error) {
\t\t\treturn dialContextWithTimeout(c, "tcp", net.JoinHostPort(ip, strconv.Itoa(port)), 4*time.Second)
\t\t},
\t\tTLSHandshakeTimeout: 5 * time.Second,
\t\tTLSClientConfig: tlsConfigWithRootCAs(parsedURL.Hostname()),
\t\tDisableCompression: true,
\t\tDisableKeepAlives: true,
\t\tForceAttemptHTTP2: false,
\t\tMaxIdleConns: 1,
\t\tMaxIdleConnsPerHost: 1,
\t}
\tdefer transport.CloseIdleConnections()

\tspeedCtx, cancel := context.WithTimeout(ctx, speedWindow)
\tdefer cancel()
\treq, err := http.NewRequestWithContext(speedCtx, "GET", parsedURL.String(), nil)
\tif err != nil { return 0, "测速请求构建失败: " + err.Error() }
\treq.Host = parsedURL.Host
\treq.Header.Set("User-Agent", "Mozilla/5.0")
\treq.Header.Set("Accept-Encoding", "identity")

\tclient := http.Client{Transport: transport}
\tresp, err := client.Do(req)
\tif err != nil {
\t\tif ctx.Err() != nil { return 0, "测速任务已终止" }
\t\treturn 0, "测速请求失败: " + err.Error()
\t}
\tdefer resp.Body.Close()
\tif resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
\t\t_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 4096))
\t\treturn 0, formatSpeedHTTPFailure(resp.StatusCode)
\t}

\tstart := time.Now()
\tbuf := make([]byte, speedBufferSize)
\twritten, readErr := io.CopyBuffer(io.Discard, io.LimitReader(resp.Body, speedMaxBytes), buf)
\tduration := time.Since(start)
\tif ctx.Err() != nil { return 0, "测速任务已终止" }
\tif written <= 0 || duration <= 0 { return 0, "测速未收到有效下载数据" }
\tif readErr != nil && speedCtx.Err() == nil && readErr != io.EOF { return 0, "测速下载失败: " + readErr.Error() }
\treturn float64(written) / duration.Seconds() / 1024, ""
}

func runNSBTask'''
s2,n=re.subn(pattern,new,s,count=1,flags=re.S)
if n != 1: raise SystemExit(f'runNSBDownloadSpeed replace count={n}')
p.write_text(s2,encoding='utf-8')

# Hard cap speed concurrency in backend too, protecting old saved browser config/manual payloads.
replace_once('combined_refactor/server.go',
'''\t\t\tif params.SpeedTest < 0 {
\t\t\t\tparams.SpeedTest = 0
\t\t\t}
\t\t\tif params.SpeedLimit < 0 {''',
'''\t\t\tif params.SpeedTest <= 0 {
\t\t\t\tparams.SpeedTest = 1
\t\t\t}
\t\t\tif params.SpeedTest > 2 {
\t\t\t\tparams.SpeedTest = 2
\t\t\t}
\t\t\tif params.SpeedLimit < 0 {''')

# Batch speed progress should count tested rows, not only rows above threshold.
replace_once('combined_refactor/tasks_nsb.go',
'''\treportNSBProgress(session, "speed", 0, speedLimit, "测速中")
\tspeedCanceled := runNSBSpeedWorkers(ctx, results, maxWorkers, speedLimit, speedMin, func(tested, qualified int) {
\t\treportNSBProgress(session, "speed", qualified, speedLimit, "测速中")''',
'''\treportNSBProgress(session, "speed", 0, len(results), "测速中")
\tspeedCanceled := runNSBSpeedWorkers(ctx, results, maxWorkers, speedLimit, speedMin, func(tested, qualified int) {
\t\treportNSBProgress(session, "speed", tested, len(results), "测速中")''')

# Tests.
replace_once('combined_refactor/proxy_local_test.go',
'''\tcfg := normalizeProxyConfig(proxyLocalTaskRequest{Attempts: 3, Threads: 60, TimeoutMS: 7000})
\tif cfg.Attempts != 3 || cfg.Threads != 60 || cfg.Timeout != 7000000000 {''',
'''\tcfg := normalizeProxyConfig(proxyLocalTaskRequest{Attempts: 3, Threads: 60, TimeoutMS: 7000})
\tif cfg.Attempts != 3 || cfg.Threads != 16 || cfg.Timeout != 7000000000 {''')
replace_once('combined_refactor/proxy_local_test.go',
'''\tif cfg.Path != "/cdn-cgi/trace" || cfg.Attempts != 1 {
\t\tt.Fatalf("unexpected defaults: %#v", cfg)
\t}''',
'''\tif cfg.Path != "/cdn-cgi/trace" || cfg.Attempts != 1 || cfg.Threads != 8 {
\t\tt.Fatalf("unexpected lightweight defaults: %#v", cfg)
\t}''')
replace_once('combined_refactor/proxy_local_integration_test.go',
'''required := []string{"CF优选IP筛选器", "start_proxy_task", "example.com", "Host 默认跟随 SNI", "一键测速", "停止测速", "请先填写实际使用的 SNI", "pageSize"}''',
'''required := []string{"CF优选IP筛选器", "start_proxy_task", "example.com", "Host 默认跟随 SNI", "一键测速", "停止测速", "请先填写实际使用的 SNI", "pageSize", "filterSpeed", "exportModal", "归属地", "当前筛选结果"}''')
replace_once('combined_refactor/proxy_local_integration_test.go',
'''\tif strings.Contains(html, "value=\\\"example.com\\\"") {
\t\tt.Fatal("SNI example must remain a placeholder, not a persisted default value")
\t}''',
'''\tif strings.Contains(html, "value=\\\"example.com\\\"") {
\t\tt.Fatal("SNI example must remain a placeholder, not a persisted default value")
\t}
\tif !strings.Contains(html, "id=\\\"threads\\\" type=\\\"number\\\" value=\\\"8\\\" min=\\\"1\\\" max=\\\"16\\\"") || !strings.Contains(html, "id=\\\"speedThreads\\\" type=\\\"number\\\" value=\\\"1\\\" min=\\\"1\\\" max=\\\"2\\\"") {
\t\tt.Fatal("V4 lightweight concurrency defaults are missing")
\t}
\tif strings.Contains(html, "data-sort=\\\"httpStatus\\\">HTTP") || strings.Contains(html, "<th>说明</th>") {
\t\tt.Fatal("HTTP/说明 columns must remain removed from the V4 result table")
\t}''')

(ROOT/'combined_refactor/proxy_geo_test.go').write_text(r'''package main

import "testing"

func TestProxyCountryLabel(t *testing.T) {
    if got := proxyCountryLabel("HK"); got != "香港（HK）" { t.Fatalf("unexpected HK label: %q", got) }
    if got := proxyCountryLabel("US"); got != "美国（US）" { t.Fatalf("unexpected US label: %q", got) }
}

func TestProxyGeoLabelPrefersCountryCity(t *testing.T) {
    got := proxyGeoLabel(proxyGeoPayload{Success: true, CountryCode: "JP", Country: "Japan", City: "Tokyo"})
    if got != "日本 · Tokyo" { t.Fatalf("unexpected geo label: %q", got) }
}
''', encoding='utf-8')
