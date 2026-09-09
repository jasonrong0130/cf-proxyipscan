//go:build windows

package main

import (
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"time"
	"unsafe"

	webview2 "github.com/jchv/go-webview2"
	"golang.org/x/sys/windows"
)

func defaultDesktopMode() bool { return true }

func runDesktopWindow(displayURL string) error {
	// 先确认本地服务已就绪，再创建原生桌面窗口。
	if err := waitForDesktopServer(displayURL); err != nil {
		showDesktopError("CF优选IP筛选器", "本地服务启动失败："+err.Error())
		return err
	}

	// 使用 Per-Monitor V2 DPI awareness，避免 Windows 高缩放下被系统位图拉伸导致发虚。
	enablePerMonitorDPI()

	dataPath := filepath.Join(os.Getenv("LOCALAPPDATA"), "CFIPSelector", "WebView2")
	if os.Getenv("LOCALAPPDATA") == "" {
		dataPath = filepath.Join(os.TempDir(), "CFIPSelector-WebView2")
	}
	_ = os.MkdirAll(dataPath, 0o755)

	w := webview2.NewWithOptions(webview2.WebViewOptions{
		Debug:     debugMode,
		AutoFocus: true,
		DataPath:  dataPath,
		WindowOptions: webview2.WindowOptions{
			Title:  "CF优选IP筛选器",
			Width:  1160,
			Height: 760,
			Center: true,
		},
	})
	if w == nil {
		showDesktopError("CF优选IP筛选器", "无法启动桌面窗口。请确认 Microsoft Edge WebView2 Runtime 已安装。")
		return errors.New("无法创建 WebView2 桌面窗口")
	}
	defer w.Destroy()

	w.SetSize(900, 620, webview2.HintMin)
	w.SetSize(1160, 760, webview2.HintNone)
	w.Navigate(displayURL)
	w.Run()
	return nil
}

func waitForDesktopServer(displayURL string) error {
	client := &http.Client{Timeout: 500 * time.Millisecond}
	deadline := time.Now().Add(4 * time.Second)
	var lastErr error
	for time.Now().Before(deadline) {
		resp, err := client.Get(displayURL)
		if err == nil {
			_ = resp.Body.Close()
			return nil
		}
		lastErr = err
		time.Sleep(100 * time.Millisecond)
	}
	if lastErr == nil {
		lastErr = errors.New("等待本地服务超时")
	}
	return lastErr
}

func enablePerMonitorDPI() {
	user32 := windows.NewLazySystemDLL("user32.dll")
	setDPIContext := user32.NewProc("SetProcessDpiAwarenessContext")
	// DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == (HANDLE)-4
	if err := setDPIContext.Find(); err == nil {
		ret, _, _ := setDPIContext.Call(uintptr(^uintptr(3)))
		if ret != 0 {
			return
		}
	}
	// Windows 8.1 及更早环境的兼容回退。
	setProcessDPIAware := user32.NewProc("SetProcessDPIAware")
	if err := setProcessDPIAware.Find(); err == nil {
		_, _, _ = setProcessDPIAware.Call()
	}
}

func showDesktopError(title, message string) {
	user32 := windows.NewLazySystemDLL("user32.dll")
	messageBoxW := user32.NewProc("MessageBoxW")
	titlePtr, _ := windows.UTF16PtrFromString(title)
	messagePtr, _ := windows.UTF16PtrFromString(message)
	const mbIconError = 0x00000010
	const mbOK = 0x00000000
	_, _, _ = messageBoxW.Call(0, uintptr(unsafe.Pointer(messagePtr)), uintptr(unsafe.Pointer(titlePtr)), mbOK|mbIconError)
}
