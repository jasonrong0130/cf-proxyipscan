//go:build windows

package main

import (
	"errors"
	"os"
	"path/filepath"
	"unsafe"

	webview2 "github.com/jchv/go-webview2"
	"golang.org/x/sys/windows"
)

func defaultDesktopMode() bool { return true }

func runDesktopWindow(displayURL string) error {
	hideConsoleWindow()

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
			Width:  1380,
			Height: 900,
			Center: true,
		},
	})
	if w == nil {
		showDesktopError("CF优选IP筛选器", "无法启动桌面窗口。请确认 Microsoft Edge WebView2 Runtime 已安装。")
		return errors.New("无法创建 WebView2 桌面窗口")
	}
	defer w.Destroy()

	w.SetSize(1024, 680, webview2.HintMin)
	w.SetSize(1380, 900, webview2.HintNone)
	w.Navigate(displayURL)
	w.Run()
	return nil
}

func hideConsoleWindow() {
	kernel32 := windows.NewLazySystemDLL("kernel32.dll")
	user32 := windows.NewLazySystemDLL("user32.dll")
	getConsoleWindow := kernel32.NewProc("GetConsoleWindow")
	showWindow := user32.NewProc("ShowWindow")

	hwnd, _, _ := getConsoleWindow.Call()
	if hwnd != 0 {
		const swHide = 0
		_, _, _ = showWindow.Call(hwnd, swHide)
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
