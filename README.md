# Recall for Homebrew

Install [Recall](https://github.com/AsherJN/recall), the free app for playing
Overwatch on Apple Silicon, with [Homebrew](https://brew.sh).

## Install

```sh
brew tap asherjn/recall
brew trust asherjn/recall
brew install --cask asherjn/recall/recall
```

Then open Recall from Applications and follow the setup steps.

## Update

```sh
brew update
brew upgrade --cask recall
```

Recall's own **Update Now** works too. Either way you get the same signed and
notarized release.

## Uninstall

```sh
brew uninstall --zap --cask recall
```

This removes Recall, Overwatch, Battle.net and everything Recall set up, the same
as Settings › Uninstall Recall in the app, including a game installed on another
drive. Everything goes to the Trash, and your Blizzard account is untouched.
Without `--zap`, only the app is removed and the game stays installed.

Already used Settings › Uninstall Recall? Run `brew uninstall --cask recall` so
Homebrew stops looking for it.

## Requirements

A Mac with Apple Silicon (M1 or newer) and macOS Tahoe 26.5 or later. Recall's
[installation guide](https://github.com/AsherJN/recall/blob/main/docs/INSTALLATION.md)
covers the rest.

## How this tap stays current

A GitHub Action checks for a new Recall release every three hours. It moves the
cask to the new version only after the download matches its published checksum
and the app inside is Recall, signed with its Developer ID and notarized by Apple.
