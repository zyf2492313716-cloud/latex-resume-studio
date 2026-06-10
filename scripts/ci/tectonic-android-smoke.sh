#!/usr/bin/env bash
set -euo pipefail

adb wait-for-device

for i in $(seq 1 60); do
  sdk="$(adb shell getprop ro.build.version.sdk | tr -d '\r')"
  boot="$(adb shell getprop sys.boot_completed | tr -d '\r')"
  echo "emulator boot check ${i}: sdk=${sdk:-unknown} boot=${boot:-unknown}"
  if [ "${boot}" = "1" ] && [ "${sdk:-0}" -ge 24 ]; then
    break
  fi
  sleep 5
done

sdk="$(adb shell getprop ro.build.version.sdk | tr -d '\r')"
test "${sdk:-0}" -ge 24

cd android
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb shell pm list packages | grep "com.zyf.latexresumestudio"
adb shell am instrument -w -r \
  com.zyf.latexresumestudio.test/androidx.test.runner.AndroidJUnitRunner
