# Humble Bundle Integration Plugin for GOG Galaxy 2.1+ (64-bit)

This plugin imports your Humble Bundle library into GOG Galaxy 2.1+ 64-bit. Based on the original community integration, it has been updated for the current GOG Galaxy client and Python 3.13, with rebuilt dependencies and an interactive configurator.

> **☕ Optional support**
>
> This integration is free and will remain free. If you'd like to support my work, you're welcome to [☕ buy me a coffee through PayPal](https://paypal.me/melcom2630). Support is entirely optional and always appreciated.

The steps below are for Windows. Dependencies are bundled; no separate Python installation is needed.

[Features](#features) | [Installation](#installation) | [Interactive Configurator](#interactive-configurator) | [First Start and Initial Sync](#first-start-and-initial-sync) | [Authentication and Local Data](#authentication-and-local-data) | [Troubleshooting](#troubleshooting) | [Credits](#credits) | [Special Thanks](#special-thanks) | [Support & Feedback](#support-feedback) | [Changelog](CHANGELOG.md)

<a id="features"></a>

## ✨ Features

* Imports your owned Humble Bundle games into GOG Galaxy
* Detects games installed through the Humble app
* Detects DRM-free games inside user-defined folders
* Installs, launches, and uninstalls supported games
* Tracks game time for games launched through the integration
* Includes an interactive configurator for initial setup and later changes

> [!NOTE]
> The current Humble website integration uses Windows HTTP services and requires Windows.

<a id="installation"></a>

## 📦 Installation

### 🔄 Automatic Installation with Plugin Updater (Recommended)

Use the [melcom GOG Galaxy Plugin Updater](https://github.com/melcom-creations/galaxy-integrations-64bit/tree/main/tools/melcom-galaxy_plugin_updater) to install or update the integration.

1. Download and extract the Plugin Updater.
2. Double-click `update-plugins.bat`.
3. Select your preferred language and follow the displayed instructions.

### 📂 Manual Installation

1. Close GOG Galaxy completely, including the system tray application.
2. Download the [latest release package](https://github.com/melcom-creations/galaxy-integration-humble/releases/latest).
3. Extract the plugin folder from the ZIP archive into:

   ```text
   %localappdata%\GOG.com\Galaxy\plugins\installed\
   ```

Place `manifest.json` directly inside this folder, without an extra nested plugin folder:

```text
%localappdata%\GOG.com\Galaxy\plugins\installed\humble_f0ca3d80-a432-4d35-a9e3-60f27161ac3a\
```

> [!IMPORTANT]
> Do not place backup copies of this plugin inside the `plugins\installed` directory. GOG Galaxy scans every folder inside this directory during startup, so duplicate plugin folders can cause GUID conflicts or load an outdated version.

**Next step:** Continue with [Interactive Configurator](#interactive-configurator), then [First Start and Initial Sync](#first-start-and-initial-sync).

<a id="interactive-configurator"></a>

## 🔧 Interactive Configurator

The interactive configurator guides you through the setup, validates your input, and writes the required configuration automatically. After successful Humble sign-in, the plugin opens it when the configuration file is missing or no DRM-free games folder is configured, including after reinstalling the plugin. It opens at most once per plugin run unless you request it manually. If setup is canceled, it is offered again on the next plugin start. Existing valid settings are reused.

The configurator lets you type the folder containing your DRM-free Humble games into a Windows path field or select it with **Browse**. In the folder picker, use **Make New Folder** to create a folder at the selected location. Backslashes, forward slashes, and an optional trailing separator are accepted.

If the selected folder is not named `Humble`, the configurator offers a separate `Humble` subfolder. Accept the offer to use or create that subfolder, or choose **No** to keep the folder you entered, such as `X:\Spiele` or `X:\Games`. Naming the folder `Humble` is optional. If you enter a path to a missing folder, the configurator asks before creating it.

You do not need to run `configurator.bat` manually during normal initial setup. To change the configuration later, double-click the **Install** button of any Humble Bundle game in GOG Galaxy. If the configurator does not open that way, double-click `configurator.bat` at:

```text
%localappdata%\GOG.com\Galaxy\plugins\installed\humble_f0ca3d80-a432-4d35-a9e3-60f27161ac3a\configurator.bat
```

### 📋 Configuration Steps

1. Select your preferred language.
2. Enter the folder containing your DRM-free Humble games or select it with **Browse**.
3. Choose whether to use the suggested `Humble` subfolder and confirm creation if needed.
4. Review and confirm the remaining settings.

Examples of valid game folders:

```text
D:\Humble
D:\Games\Humble
D:\Games
D:\Games\Humble\
```

Extract each DRM-free game into its own subfolder inside a configured game folder, with the game's executable directly inside that subfolder. On Windows, the plugin can also match the executable's product title when the archive folder has a different name, such as `DayOfTheTentacle_Win32_NoSteam_v1.8_20210106`. Configured folders are checked periodically, so newly extracted games can appear as installed without restarting Galaxy.

### 📝 Configuration File

The configurator writes `galaxy-humble-config.ini` at the location listed under [Data Storage](#data-storage-and-what-disconnect-removes). Despite its `.ini` extension, this file uses TOML syntax. Manual editing is optional; the plugin reloads saved changes automatically.

```toml
[library]
sources = [ "keys", "drm-free" ]
show_revealed_keys = false

[installed]
search_dirs = [ "E:/Spiele/Humble" ]
```

| Setting | Meaning |
|---|---|
| `sources` | Which game sources to import: `keys` includes games supplied through third-party keys; `drm-free` includes games available as direct downloads. |
| `show_revealed_keys` | Whether to include key entries whose keys have already been revealed. `false` hides these entries. Revealing a key does not prove that it was activated on another platform. |
| `search_dirs` | Folders scanned for installed DRM-free Humble games. More than one folder can be listed. |

The configurator writes Windows paths with forward slashes, such as `E:/Spiele/Humble`, to avoid backslash escaping. If editing a double-quoted TOML path manually, each backslash must be doubled: `"E:\\Spiele\\Humble"`.

<a id="first-start-and-initial-sync"></a>

## 🚀 First Start and Initial Sync

For the first synchronization after installing, updating, or configuring the plugin:

1. If you use the Humble app, start it and keep it open.
2. Start GOG Galaxy.
3. Connect the Humble Bundle integration through **Settings -> Integrations** if necessary.
4. Complete sign-in in your Windows default browser. The dedicated login window closes automatically, and its temporary profile is removed. Complete the interactive configuration when it opens.
5. Open the account menu in the top-right corner and select **Sync integrations**.
6. Wait until the synchronization has finished.

While Humble reports that purchase migration is still in progress, the integration retains previously imported games if they are temporarily absent from the website.

<a id="authentication-and-local-data"></a>

## 🔒 Authentication and Local Data

Confirm **Connect** in Galaxy's account connection dialog to begin sign-in. The displayed Galaxy sign-in window then opens your Windows default browser with a dedicated temporary profile. Galaxy stores the Humble session cookies as integration credentials. The browser closes and its temporary profile is removed after sign-in.

Galaxy also displays a small waiting window to complete the connection. Keep it open while signing in through the browser; it closes automatically when the connection is complete.

<a id="data-storage-and-what-disconnect-removes"></a>

### 💾 Data Storage and What Disconnect Removes

| Data | Local location | Result of clicking **Disconnect** |
|---|---|---|
| Humble session cookies used for authentication | Galaxy's credential area inside `%ProgramData%\GOG.com\Galaxy\storage\plugins\humble_f0ca3d80-a432-4d35-a9e3-60f27161ac3a-<Galaxy-user-id>-storage.db` | Removed by Galaxy |
| Cached Humble library and locally tracked game time | The normal cache area inside the same Galaxy plugin database | The local cache can remain |
| Library filters and configured DRM-free game folders | `%LOCALAPPDATA%\melcom-creations\GOG Galaxy Integrations\Humble\galaxy-humble-config.ini` | Remains |
| Temporary login browser profile | `%TEMP%\melcom-humble-auth-<browser>-<random>\` | Removed after completed sign-in or normal plugin shutdown |

The plugin and interactive configurator use the same configuration file. On startup, an existing `%LOCALAPPDATA%\galaxy-hb\galaxy-humble-config.ini` is moved to the new location with its contents preserved. If a configuration already exists at the new location, that file takes priority and the old file is left untouched.

<a id="troubleshooting"></a>

## 🛠️ Troubleshooting

Restart Galaxy and try one synchronization. If the problem remains, collect a fresh log. A database reset is not required for this.

### 🧪 Create a Fresh Diagnostic Log

1. Close GOG Galaxy completely, including the system tray application.
2. Open `%ProgramData%\GOG.com\Galaxy\logs\`. Move the existing `plugin-humble-f0ca3d80-a432-4d35-a9e3-60f27161ac3a.log` to a backup folder outside this directory, if present. Leave other logs in place.
3. If used, start the Humble app. Start Galaxy, reproduce the problem once, then close Galaxy completely to finish writing the log.
4. Send the newly created plugin log, not the entire folder. Include the plugin and Galaxy versions, your steps, the expected and actual result, and whether the problem can be reproduced.

See [Support & Feedback](#support-feedback) for contact options.

### 🔄 Reset Plugin Storage (Last Resort)

Use this only if restarting and synchronizing do not help, or when requested for troubleshooting. Cached library data and local playtime may be lost; signing in again may be required. Keep the backup.

1. Close GOG Galaxy completely, including the system tray application.
2. Open `%ProgramData%\GOG.com\Galaxy\storage\plugins\`.
3. Find the active `humble_...-storage.db` file for your Galaxy account. If unsure which file is correct, stop. Leave other integrations' databases unchanged.
4. Append `.old` to its name. If that backup already exists, use an unused suffix; never overwrite it.
5. If used, start the Humble app. Start Galaxy, reconnect if necessary, and select **Sync integrations** once. Wait until it finishes.

To undo: close Galaxy, rename the new database to an unused backup name, then restore the saved database's original name. Never restore it while Galaxy is running.

<a id="credits"></a>

## 🙏 Credits

**Original Plugin Author**  
Mesco

**Original Project**  
[UncleGoogle/galaxy-integration-humblebundle](https://github.com/UncleGoogle/galaxy-integration-humblebundle)

**64-bit Port, Python 3.13 Compatibility, Dependency Modernization and Configurator**  
melcom

<a id="special-thanks"></a>

## ❤️ Special Thanks

I want to take a moment to thank the people who kept me going during this intense development phase:

* A huge thank you to my friend [**Hustlefan**](https://www.gog.com/u/Hustlefan). Over the past few days, you've been much more than just moral support. You gave me the encouragement I needed, patiently put up with all my Discord spam, and helped beta test the plugins. I'm really happy that you're pleased with the results. Thanks so much for all your support, my friend.

* And a big thank you to my girlfriend [**Florence H.** (fl0H0815)](https://www.gog.com/u/Florence_Heart). While she was enjoying the good life at her parents' place - complete with air conditioning and a huge swimming pool - she kept my spirits up by sending me photos of herself, her friends, her parents, and even her parents' dog. She reminded me that there's a wonderful world outside of a code editor every now and then... 🙈

  *Now that's what I call real support.* ❤️

Thank you both for having my back!

<a id="support-feedback"></a>

## 🤝 Support & Feedback

**GitHub Issues are intentionally disabled.** Health-related limitations prevent me from reliably managing separate issue trackers across all of my plugin repositories.

Before contacting me, follow [Troubleshooting](#troubleshooting) and prepare a fresh Humble Bundle plugin log with a detailed description.

* **GOG:** Send me a message or add me as a friend through my [GOG profile](https://www.gog.com/u/melcom).
* **Email:** `melcom @ gmx.net`
* **Discord:** `.melcom` - the leading dot is part of the username. You can send me a message or add me as a friend.

Logs can be attached directly or shared using an accessible cloud storage link, such as Dropbox, OneDrive, Google Drive, or a similar service. Response times may vary depending on my health and available development time. Thank you for your understanding.
