APP     = AOE2分析工具
MAIN    = launcher.py
DIST    = dist/$(APP)

.PHONY: build clean install-deps

## 打包成 exe（輸出到 dist/AOE2分析工具/）
build:
	python -m PyInstaller \
		--onedir \
		--windowed \
		--name "$(APP)" \
		--clean \
		$(MAIN)
	@echo.
	@echo 完成！exe 位置：$(DIST)/$(APP).exe
	@echo 請確認 scripts/ 和 data/ 資料夾已複製到同目錄

## 安裝打包所需套件
install-deps:
	pip install pyinstaller

## 清除打包產出
clean:
	rm -rf build dist *.spec
