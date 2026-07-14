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
# Maintainers: bump `tag` and `revision` on each release (see docs/PUBLISHING.md).
class ClaudeUsageMeter < Formula
  desc "macOS menu-bar widget for Claude Pro/Max/Team plan usage (SwiftBar/xbar plugin)"
  homepage "https://github.com/billjoel25/claude-usage-meter"
  url "https://github.com/billjoel25/claude-usage-meter.git",
      tag:      "v1.2.0",
      revision: "REPLACE_WITH_TAG_COMMIT_SHA"
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
