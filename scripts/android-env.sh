#!/usr/bin/env bash
# Tideline Android shell development environment
# Usage: source ~/VSCodeWorkspace/personal/tideline/scripts/android-env.sh
#
# Or add this line to ~/.zshrc for permanent setup:
#   source ~/VSCodeWorkspace/personal/tideline/scripts/android-env.sh

# JDK 21 (bundled with Android Studio as JetBrains Runtime; required for LiteRT-LM Java 21 bytecode)
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
export PATH="$JAVA_HOME/bin:$PATH"

# Android SDK from android-commandlinetools cask
export ANDROID_HOME="/opt/homebrew/share/android-commandlinetools"
export ANDROID_SDK_ROOT="$ANDROID_HOME"

# Add platform-tools (adb) and emulator to PATH
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"

# Quick helpers
alias avd-start='emulator -avd Pixel8Pro_API35 -no-snapshot-save > /tmp/emulator.log 2>&1 &'
alias avd-list='avdmanager list avd'
alias devices='adb devices'
alias gallery-launch='adb shell am start -n com.google.ai.edge.gallery/.MainActivity'
alias gallery-screenshot='adb exec-out screencap -p > /tmp/gallery.png && open /tmp/gallery.png'
