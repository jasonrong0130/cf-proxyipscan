//go:build !windows

package main

import "errors"

func defaultDesktopMode() bool { return false }

func runDesktopWindow(displayURL string) error {
	_ = displayURL
	return errors.New("桌面窗口模式当前仅支持 Windows")
}
