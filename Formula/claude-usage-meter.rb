# Optional Homebrew formula. See docs/PUBLISHING.md.
#
# Install:
#   brew tap billjoel25/claude-usage-meter https://github.com/billjoel25/claude-usage-meter
#   brew install billjoel25/claude-usage-meter/claude-usage-meter
#
# Homebrew can't place a file into your (user-chosen) SwiftBar plugin folder, so
# this installs the script into the Homebrew prefix and the caveats below tell you
# how to symlink it. For most people the curl one-liner in the README is simpler.
#
# Maintainers: on each release, bump `version`, the `url` tag, and `sha256`
# (= shasum -a 256 claude-usage.5m.py at that tag). See docs/PUBLISHING.md.
class ClaudeUsageMeter < Formula
  desc "macOS menu-bar widget for Claude Pro/Max/Team plan usage (SwiftBar/xbar plugin)"
  homepage "https://github.com/billjoel25/claude-usage-meter"
  url "https://raw.githubusercontent.com/billjoel25/claude-usage-meter/v1.2.0/claude-usage.5m.py"
  version "1.2.0"
  sha256 "7d4f95ca56ae27c45877715a5b36fefdaf5e8b9659612aa848d240314061f79d"
  license "MIT"
  head "https://github.com/billjoel25/claude-usage-meter.git", branch: "main"

  depends_on :macos

  def install
    libexec.install "claude-usage.5m.py"
  end

  def caveats
    <<~EOS
      This is a SwiftBar/xbar plugin, so it must live in your plugin folder.
      Symlink it there (adjust the path if your SwiftBar Plugin Folder differs):

        ln -sf "#{libexec}/claude-usage.5m.py" \\
          "$HOME/Library/Application Support/SwiftBar/Plugins/claude-usage.5m.py"

      Need SwiftBar?   brew install --cask swiftbar
      Then click the Claude icon in the menu bar to sign in.
    EOS
  end

  test do
    assert_path_exists libexec/"claude-usage.5m.py"
    assert_match "python3", (libexec/"claude-usage.5m.py").read.lines.first
  end
end
