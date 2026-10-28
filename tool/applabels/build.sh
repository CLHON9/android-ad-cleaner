#!/bin/bash
# 重新生成 tool/applabels.dex（随源码提交，打包时带上）。需要 JDK 11+ 和 Android SDK（platforms + build-tools）。
set -euo pipefail
cd "$(dirname "$0")"
SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
JAR="$(ls -d "$SDK"/platforms/android-*/android.jar | sort -V | tail -1)"
D8="$(ls -d "$SDK"/build-tools/*/d8 | sort -V | tail -1)"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT
javac --release 8 -cp "$JAR" -d "$OUT/classes" Labels.java 2>/dev/null || javac -source 8 -target 8 -cp "$JAR" -d "$OUT/classes" Labels.java
"$D8" --min-api 21 --release --output "$OUT" "$OUT"/classes/aac/*.class
cp "$OUT/classes.dex" ../applabels.dex
shasum -a 256 ../applabels.dex
