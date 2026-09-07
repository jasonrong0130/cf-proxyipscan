package main

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
	if code == "" {
		return ""
	}
	if name := proxyCountryZH[code]; name != "" {
		return name + "（" + code + "）"
	}
	return code
}

func proxyGeoLabel(data proxyGeoPayload) string {
	code := strings.ToUpper(strings.TrimSpace(data.CountryCode))
	country := proxyCountryZH[code]
	if country == "" {
		country = strings.TrimSpace(data.Country)
	}
	if country == "" {
		country = code
	}
	city := strings.TrimSpace(data.City)
	if city == "" {
		city = strings.TrimSpace(data.Region)
	}
	if country == "" {
		return city
	}
	if city != "" && !strings.EqualFold(city, country) {
		return country + " · " + city
	}
	if code != "" && country != code {
		return country + "（" + code + "）"
	}
	return country
}

func lookupProxyGeo(ctx context.Context, ip string) string {
	ip = strings.TrimSpace(ip)
	parsed := net.ParseIP(ip)
	if parsed == nil || parsed.IsLoopback() || parsed.IsPrivate() || parsed.IsUnspecified() {
		return ""
	}
	if cached, ok := proxyGeoCache.Load(ip); ok {
		return cached.(string)
	}
	select {
	case proxyGeoSem <- struct{}{}:
		defer func() { <-proxyGeoSem }()
	case <-ctx.Done():
		return ""
	}
	if cached, ok := proxyGeoCache.Load(ip); ok {
		return cached.(string)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, "https://ipwho.is/"+url.PathEscape(ip), nil)
	if err != nil {
		return ""
	}
	req.Header.Set("User-Agent", "CF-IP-Selector/1.0")
	resp, err := proxyGeoClient.Do(req)
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return ""
	}
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
	if err != nil {
		return ""
	}
	var data proxyGeoPayload
	if json.Unmarshal(raw, &data) != nil || !data.Success {
		return ""
	}
	label := proxyGeoLabel(data)
	if label != "" {
		proxyGeoCache.Store(ip, label)
	}
	return label
}

func enrichProxyLocation(ctx context.Context, result *proxyLocalResult) {
	if result == nil {
		return
	}
	if code := strings.TrimSpace(result.Loc); code != "" {
		result.Location = proxyCountryLabel(code)
		result.LocationSource = "出口"
		return
	}
	if result.Status != "success" {
		return
	}
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
