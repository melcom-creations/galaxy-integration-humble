# Changelog

## Version 2.0.5-64bit

### Overview
Maintenance release. Rebuilt all third-party dependencies as clean 64-bit wheels for Python 3.13 via `melcom's Galaxy Plugin Scout v1.1.10`.

### Changed
- **Dependency rebuild:** All third-party packages in `/modules/` were removed and reinstalled as verified 64-bit (`cp313-win_amd64`) wheels. All packages now carry proper `.dist-info` metadata, enabling fully automatic dependency management in future maintenance runs.
- **`galaxy_plugin_api` now pip-managed:** The GOG Galaxy Plugin API (`galaxy/`) is now installed and updated via `pip install galaxy_plugin_api` instead of being treated as static bundled code.

### Packages rebuilt (64-bit)
`aiohappyeyeballs`, `aiohttp`, `aiosignal`, `async_timeout`, `attrs`, `certifi`, `frozenlist`, `galaxy_plugin_api`, `idna`, `multidict`, `propcache`, `psutil`, `toml`, `typing_extensions`, `yarl`

---

## Version 2.0.4-64bit

[Overview]
This release hardens the new interactive configuration workflow with stricter path validation, safer folder creation prompts, clearer error messaging, and smoother step progression after automatic directory creation.

[Fixed]
- Fixed the language selection and step 1 path validation flow so invalid input no longer triggers repeated or confusing prompts.
- Fixed step 1 directory handling so a newly created folder now advances directly to step 2 instead of forcing the user to enter the path again.
- Fixed path validation so single drive letters, bare drive roots, and incomplete Windows paths are rejected with clear warnings.
- Fixed the root-path warning flow so bare root paths such as `C:\` or `D:\` receive an explicit confirmation prompt instead of being treated like normal game directories.
- Fixed user-facing path examples and error messages so they now show a clean single-backslash format such as `D:\Humble` or `D:\Spiele\Humble` in the terminal output.
- Fixed the English and German configurator prompts so both language branches receive the same validation and navigation behavior.

[Changed]
- Hardened the configurator's path validation logic to require a real Windows directory structure before offering folder creation.
- Improved the step 1 error display so validation messages remain readable without stacking multiple repeated lines.
- Refined the directory creation branch to continue the setup flow automatically after success.
- Tightened the wording of the configuration prompts to better distinguish between invalid paths, missing folders, and risky root-level locations.

[Technical Breakdown]

### 1. Path validation hardening
Files: `configurator.bat`, `configurator.ps1`

The directory input flow now rejects incomplete values such as a lone drive letter or a bare root path before any creation logic runs. Valid paths must represent an actual Windows folder target, which prevents accidental acceptance of non-path input.

### 2. Safer directory creation flow
Files: `configurator.bat`, `configurator.ps1`

When a valid path points to a missing folder, the configurator now returns the expected create-folder confirmation prompt. After successful creation, the setup proceeds to the next step automatically instead of looping back to step 1.

### 3. Cleaner error presentation
Files: `configurator.bat`, `configurator.ps1`

Validation messages were standardized to avoid repeated stacked errors and to keep the terminal output readable during repeated failed input attempts. Root-level warnings and invalid-path messages are now easier to distinguish for both German and US-English users.


## Version 2.0.3-64bit

[Overview]
This release significantly improves the user configuration experience by introducing an interactive command-line configurator, adds automatic real-time playtime tracking for DRM-free games, and hardens configuration management to prevent GOG Galaxy from accidentally overwriting custom user settings.

[Added]
- **Interactive Batch Configurator (`configurator.bat`):** Created a terminal-based configuration utility. Selecting "Configure" in GOG Galaxy now launches this interactive CLI tool to safely write pristine TOML configurations instead of opening the raw text file.
- **Real-Time Playtime Tracking:** Enabled background monitoring of running game processes. The plugin now captures start and end timestamps, translates active sessions to playtime minutes, updates last played dates, and pushes synchronization stats to GOG Galaxy in real-time.

[Fixed]
- Fixed a critical `plugin.py` syntax error on import (`_maybe_open_install_config` parenthesis typo) [plugin-humble-f0ca3d80-a432-4d35-a9e3-60f27161ac3a.log].
- Fixed a configuration overwrite issue where GOG Galaxy's default initialization could silently reset custom `search_dirs` and `sources` settings to defaults.

[Changed]
- Playtime calculations now kaufmännisch-round (nearest minute) rather than strict truncation to ensure shorter playing sessions are recorded properly.
- Hardened GOG's manual configuration-trigger to open the custom batch configurator on Windows instead of the raw text editor [settings.py].

[Technical Breakdown]

### 1. Interactive Batch Setup
Files: `settings.py`, `configurator.bat`

GOG's configuration hook has been adapted to launch the new command-line configurator on Windows. The tool guides users step-by-step through setting game directories and choosing library source priorities using strictly validated inputs, outputting structurally valid TOML without syntax errors [settings.py].

### 2. Safeguarding Custom Configuration
Files: `plugin.py`

Modified `_maybe_open_install_config` to check if `LOCAL_CONFIG_FILE` exists before attempting to save a default configuration template. This prevents GOG Galaxy from wiping custom-written configuration values with standard default templates during the initial installation workflow [plugin.py].

### 3. Active Session Playtime Logging
Files: `plugin.py`

Integrated session-tracking hooks inside the periodic `_check_statuses` routine. The plugin monitors `LocalGameState.Running` state changes to calculate playing duration, which is then saved to GOG's persistent cache and exposed back to GOG Galaxy's UI [plugin.py].



## Version 2.0.2-64bit

[Overview]
This maintenance release focuses on robustness, safer error handling, and reduced background overhead. The plugin now handles unexpected subscription metadata more gracefully, avoids unnecessary local rescans, and improves resilience during long-running synchronization operations.

[Fixed]
- Removed a hard plugin-abort condition when unexpected Humble Choice subscription identifiers are encountered.
- Unexpected subscription metadata no longer terminates the plugin through an assertion failure.
- Improved resilience against malformed or previously unknown subscription naming formats.
- Reduced the likelihood of unnecessary local synchronization work being triggered repeatedly.

[Changed]
- Subscription normalization now uses defensive fallback handling instead of a hard assertion path.
- Local game scanning behavior was refined to avoid excessive rescan requests when no meaningful state change occurred.
- Internal synchronization paths were reviewed to reduce avoidable background workload while preserving existing functionality.
- Background update routines are more tolerant of transient data inconsistencies.

[Technical Breakdown]

### 1. Subscription parsing hardening
Files: `plugin.py`

The previous implementation contained a hard `assert False` path when encountering an unexpected subscription identifier. This has been replaced with defensive handling so previously unseen Humble subscription formats cannot terminate the plugin.

### 2. Rescan optimization
Files: `plugin.py`

Local scan scheduling was adjusted to avoid unnecessary repeated rescan requests. Existing installed-game detection behavior remains unchanged while reducing avoidable background activity.

### 3. Synchronization stability improvements
Files: `plugin.py`

Several internal synchronization paths were hardened to better tolerate temporary inconsistencies and unexpected remote data without interrupting normal plugin operation.



## Version 2.0.1-64bit

[Fixed]
- Restored the original double-click behavior on the Install button.
- Fixed a regression where the configuration window was no longer opened when double-clicking Install.
- Reconnected the existing double-click handler to the Humble Bundle installation workflow.
- Double-clicking Install now opens the Humble Bundle configuration file again, allowing the installation path to be adjusted as intended.
- Prevented the normal installation/download workflow from starting when the double-click configuration action is triggered.
- Preserved the standard single-click Install behavior without any functional changes.

## Version 2.0.0-64bit

[Added]
- Credits: melcom added as the author of the 64-bit fixes and optimizations.

[Changed]
- Upgraded the plugin for full compatibility with the GOG Galaxy 64-bit client (v2.1+) and Python 3.13.
- Replaced legacy 32-bit dependencies with native 64-bit compiled binaries (`aiohttp`, `yarl`, `frozenlist`, `multidict`, `pycparser`, `cffi`, and `psutil`).
- Upgraded `pythonnet` from v2.5.2 to v3.1.0 and integrated `clr_loader` (v0.3.1) to resolve .NET GUI errors under Python 3.13.
- Simplified the first-time setup workflow.

[Fixed]
- Fixed instant crashes on Python 3.12+ (GOG 2.1) by removing deprecated `distutils.version` (`LooseVersion`) imports and replacing the version verification with robust, native integer-tuple comparisons [1].
- Fixed missing dependency issues for modern `aiohttp` and `yarl` by adding `propcache` and `aiohappyeyeballs`.
- Disabled outdated Sentry SDK telemetry logging/initialization to prevent background stream contamination (stdin/stdout JSON-RPC conflicts).
- Added warnings filtering to prevent Python 3.13 deprecation messages from breaking the Galaxy communication.
- Removed `update_url` from the manifest to prevent GOG from automatically overwriting and breaking these custom 64-bit fixes.

[Removed]
- Removed the legacy Toga GUI stack (`toga`, `toga_core`, `toga_winforms`, `travertino`) and related configuration dependencies. The key display dialog was replaced with a direct link to the Humble Bundle Keys page.
- Removed unnecessary bundled libraries and test components that are no longer required for normal plugin operation.


## Version 0.11.0
[Added]
- Humble App Support - install, launch, uninstall, getting game size andinstallation state

Collection and Vault games are shown under Subscriptions tab in separate categories.
How to set bookmark, see:
https://github.com/UncleGoogle/galaxy-integration-humblebundle/#recommended-humble-choice-view

[Fixed]
- Adjusting to humble API changes in May 2022 #183
- Error handling in case of authorisation cookie invalidation #179

## Version 0.10.0

[Fixed]
- Error handling bug introduced in 0.9.5
- Rework getting subscriptions list #165 #167
- Adjust to new Choice subscription model introduced on March 2022 #172 
- Update and re-set sentry sdk
- Not showing choice month games if there was no extras list (eg. Humble Choice 12-2021)

[Changed]
- Use new bulk API for fetching orders list #168 
- Move the last Choice month to the top of subscription list in Galaxy Settings>Features window

[Removed]
- Trove support (Humble Choice Collection suppport is planned in the future)

## Version 0.9.5
(!) WARNING: If you're Humble subscriber, plugin reconnection is needed to sync subscriptions again (!)

[Fixed]
- Error while loading a subscriptions list (humble choice and Trove games not visible) #161
- Multi-game keys from bundles: no longer returns game title with leading "and" #157 @ 5dd53f0 by @Gwindalmir
- Mutli-game keys from bundles: list of games titles that should not be splitted is now case insensitive #157 @ d95cd550 by @Gwindalmir
- GUI: misleading tooltip information @ f96edbd

## Version 0.9.4
(!) WARNING: If you're Humble subscriber, plugin reconnection is needed to sync subscriptions again (!)

[Fixed]
- Plugin being offline for subscribers and no subscriptions shown in Settings->Features #151

## Version 0.9.1
[Fixed]
- Showing subscriptions (adjusting to changes in humble API again) #139
- Typo in subscription months (thanks @Oxenoth)

## Version 0.9.1

[Fixed]
- Showing subscriptions #136
## Version 0.9.0

[Added]
- Importing game sizes #135
- Info when particular game was added to Trove #134

[Fixed]
- Getting Trove games #133
- Loading GUI on Mac by removing non UTF8 character from CHANGELOG @ 9478b62


## Version 0.8.1
Addressed issues: https://github.com/UncleGoogle/galaxy-integration-humblebundle/milestone/6

[Fixed]
- Not showing games due to unsupported platform id #125 @ 84a7e50
- Splitting multigame key by using blacklist #124
- Show Install button for all keys #132
- Fix failing on parsing installed games when non-local uninstaller is used ("Blades of Avernum" case) #127

## Version 0.8.0

[Added]
- Humble Choice support #108; see how to set Humble Choice bookmark:
https://github.com/UncleGoogle/galaxy-integration-humblebundle#recommended-humble-choice-view

[Changed]
- Trove as subscription #102; trove access is automatically detected but it can be overwritten from Galaxy Settings -> Features
- Installed games detection: limit executable search to root level #119

[Fixed]
- Downloading DRM-free games #97
- Not showing claimed choices #113


## Version 0.7.1

[Fixed]
- GUI: fix showing (add missing changelog) on stable branch
- psutil: security update to 5.6.6

[Changed]
- GUI: rate of loading library settings decreased to ~0.3/sec to protect Galaxy from expensive operations #91

## Version 0.7.0

[Added]
- Graphical User Interface for configuration. It can be opened by double clicking "Install" button on any Humble game.
- Ability to import predefined tags: `Key`, `Unrevealed` and `Trove` to library. This won't add tags for newly appeared games automatically. You have to reimport them manually by going to Settings -> Features -> Import button under "HUMBLE BUNDLE".
- Support for keys containing multiple games at once.
- Automatic updates to integration downloaded manually from https://github.com/UncleGoogle/galaxy-integration-humblebundle/releases (this is "latest" version channel - new versions come eariler but are less stable than integrtion downloaded via Galaxy)

## Version 0.6.0

[Added]
- Config: open config by double clicking "Install" button of any HumbleBundle game (#74)
- Trove: get (scrap) ALL recent games (previously only humble trove API was used in which most recent games appears with a week or two delay (#79)

[Changed]
- Config: config file was moved outside of the plugin code (#80) to:
    - Windows: `%LocalAppData%/galaxy-hb/galaxy-humble-config.ini`
    - Mac: `~/.config/galaxy-humble.cfg`
- Config: dropped caching previous config (no need now)

[Fixed]
- Fix "no loading library" bug caused by titles longer than 100chars (#76)
- Fix plugin crashes (IndexError) while checking installed games (eg. when game "Caffeine" was installed) (#77)
- Fix release job (#72)