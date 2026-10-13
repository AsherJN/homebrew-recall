cask "recall" do
  version "1.3.0"
  sha256 "dbe066d52fc41825b4d0afc146a0d81561c6e729319f8939a2de2a733bef2b16"

  url "https://github.com/AsherJN/recall/releases/download/v#{version}/Recall-#{version}.dmg"
  name "Recall"
  desc "Play Overwatch on Apple Silicon"
  homepage "https://github.com/AsherJN/recall"

  livecheck do
    url :url
    strategy :github_latest
  end

  # Recall also updates itself. The cask leaves out `auto_updates` so that a plain
  # `brew upgrade` keeps it current too. Recall itself requires macOS 26.5.
  depends_on arch: :arm64
  depends_on macos: :tahoe

  app "Recall.app"

  # Homebrew runs this on every upgrade as well, so it never touches the game.
  uninstall quit: "org.overwatch2mac.launcher"

  # Removes what Settings › Uninstall Recall removes: Overwatch, Battle.net and
  # everything Recall set up, including a game installed on another drive. Like
  # the app, it closes Battle.net and Overwatch first and moves files to the Trash.
  zap script: {
        executable: "/bin/sh",
        args:       ["-c", <<~SH],
          id=org.overwatch2mac.launcher
          standard="$HOME/Library/Application Support/Overwatch2Mac"
          custom=$(/usr/bin/defaults read "$id" installLocation 2>/dev/null)

          # A folder Recall made: it holds the marker Recall writes into it.
          recall_folder() {
            case $1 in /*) ;; *) return 1 ;; esac
            [ "$1" != / ] && [ "$1" != "$HOME" ] && [ -d "$1" ] && [ ! -L "$1" ] &&
              [ "$(/usr/bin/head -c 19 "$1/.overwatch-2-mac-owner" 2>/dev/null)" = ow2-native-setup-v1 ]
          }

          # Ends the folder's Wine session, which closes Battle.net and Overwatch.
          close_game() {
            runtime=$(/usr/bin/plutil -extract active_runtime raw -o - "$1/state.json" 2>/dev/null) || return 0
            case $runtime in "" | [._-]* | *[!A-Za-z0-9._-]*) return 0 ;; esac
            server="$1/runtimes/$runtime/bin/wineserver"
            [ -x "$server" ] || return 0
            WINEPREFIX="$1/environment" TMPDIR="$1/tmp" HOME="$1/home" "$server" -k 2>/dev/null
            return 0
          }

          for folder in "$standard" "$custom"; do
            [ -n "$folder" ] && recall_folder "$folder" && close_game "$folder"
          done

          # A game on another drive goes to that drive's Trash.
          if [ -n "$custom" ] && [ "$custom" != "$standard" ]; then
            if recall_folder "$custom"; then
              /usr/bin/trash -s "$custom" || exit 1
            else
              echo "Recall's game folder wasn't found at $custom."
              echo "If that drive isn't connected, delete the folder once it is."
            fi
          fi

          # The graphics caches macOS keeps for Recall and for Overwatch.
          cache=$(/usr/bin/getconf DARWIN_USER_CACHE_DIR)
          for item in org.overwatch2mac.launcher org.overwatch2mac.overwatch; do
            [ -e "$cache$item" ] && /usr/bin/trash "$cache$item"
          done
          /usr/bin/defaults delete "$id" 2>/dev/null
          exit 0
        SH
      },
      trash:  [
        "~/Library/Application Support/Overwatch2Mac",
        "~/Library/Caches/org.overwatch2mac.launcher",
        "~/Library/Preferences/org.overwatch2mac.launcher.plist",
        "~/Library/Saved Application State/org.overwatch2mac.launcher.savedState",
      ]
end
