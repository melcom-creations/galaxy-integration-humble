# Humble Bundle Integration Plugin for GOG Galaxy 2.1+ (64-bit)

This plugin imports your Humble Bundle library into GOG Galaxy 2.1+ 64-bit. Based on the original community integration, it has been updated for the current GOG Galaxy client and Python 3.13, with rebuilt dependencies and an interactive configurator.

The steps below are for Windows. Dependencies are bundled; no separate Python installation is needed.

[Installation](#-installation) | [First Start](#-first-start-and-initial-sync) | [Troubleshooting](#-troubleshooting) | [Support & Feedback](#-support--feedback)

## ✨ Features

* Imports your owned Humble Bundle games into GOG Galaxy
* Detects games installed through the Humble app
* Detects DRM-free games inside user-defined folders
* Installs, launches, and uninstalls supported games
* Tracks game time for games launched through the integration
* Includes an interactive configurator for initial setup and later changes

> [!NOTE]
> macOS compatibility may be technically possible, but it is currently untested because I do not have access to a Mac. If you use macOS and would like to help test the integration, feel free to contact me.

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

**Next step:** Continue with [Interactive Configurator](#-interactive-configurator), then [First Start and Initial Sync](#-first-start-and-initial-sync).

## 🔧 Interactive Configurator

The interactive configurator guides you through the setup, validates your input, and writes the required configuration automatically. It opens the first time you connect the Humble Bundle integration through GOG Galaxy. The old manual configuration workflow is no longer recommended.

The configurator lets you select the folders containing your DRM-free Humble games. It validates every path and warns you before creating a missing directory or accepting a potentially unsafe root location.

To change the configuration later, double-click the **Install** button of any Humble Bundle game in GOG Galaxy. If the configurator does not open that way, start it manually from:

```text
%localappdata%\GOG.com\Galaxy\plugins\installed\humble_f0ca3d80-a432-4d35-a9e3-60f27161ac3a\configurator.bat
```

### 📋 Configuration Steps

1. Select your preferred language.
2. Enter the folder containing your DRM-free Humble games.
3. Confirm folder creation if the directory does not exist.
4. Review and confirm the remaining settings.

Examples of valid game folders:

```text
D:\Humble
D:\Games\Humble
```

## 🚀 First Start and Initial Sync

For the first synchronization after installing, updating, or configuring the plugin:

1. If you use the Humble app, start it and keep it open.
2. Start GOG Galaxy.
3. Connect the Humble Bundle integration through **Settings -> Integrations** if necessary.
4. Complete the interactive configuration when it opens.
5. Open the account menu in the top-right corner and select **Sync integrations**.
6. Wait until the synchronization has finished.

## 🛠️ Troubleshooting

Restart Galaxy and try one synchronization. If the problem remains, collect a fresh log. A database reset is not required for this.

### 🧪 Create a Fresh Diagnostic Log

1. Close GOG Galaxy completely, including the system tray application.
2. Open `%ProgramData%\GOG.com\Galaxy\logs\`. Move the existing `plugin-humble-f0ca3d80-a432-4d35-a9e3-60f27161ac3a.log` to a backup folder outside this directory, if present. Leave other logs in place.
3. If used, start the Humble app. Start Galaxy, reproduce the problem once, then close Galaxy completely to finish writing the log.
4. Send the newly created plugin log, not the entire folder. Include the plugin and Galaxy versions, your steps, the expected and actual result, and whether the problem can be reproduced.

See [Support & Feedback](#-support--feedback) for contact options.

### 🔄 Reset Plugin Storage (Last Resort)

Use this only if restarting and synchronizing do not help, or when requested for troubleshooting. Cached library data and local playtime may be lost; signing in again may be required. Keep the backup.

1. Close GOG Galaxy completely, including the system tray application.
2. Open `%ProgramData%\GOG.com\Galaxy\storage\plugins\`.
3. Find the active `humble_...-storage.db` file for your Galaxy account. If unsure which file is correct, stop. Leave other integrations' databases unchanged.
4. Append `.old` to its name. If that backup already exists, use an unused suffix; never overwrite it.
5. If used, start the Humble app. Start Galaxy, reconnect if necessary, and select **Sync integrations** once. Wait until it finishes.

To undo: close Galaxy, rename the new database to an unused backup name, then restore the saved database's original name. Never restore it while Galaxy is running.

## 🙏 Credits

**Original Plugin Author**  
Mesco

**Original Project**  
[UncleGoogle/galaxy-integration-humblebundle](https://github.com/UncleGoogle/galaxy-integration-humblebundle)

**64-bit Port, Python 3.13 Compatibility, Dependency Modernization and Configurator**  
melcom

## ❤️ Special Thanks

I want to take a moment to thank the people who kept me going during this intense development phase:

* A huge thank you to my friend [**Hustlefan**](https://www.gog.com/u/Hustlefan). Over the past few days, you've been much more than just moral support. You gave me the encouragement I needed, patiently put up with all my Discord spam, and helped beta test the plugins. I'm really happy that you're pleased with the results. Thanks so much for all your support, my friend.

* And a big thank you to my girlfriend [**Florence H.** (fl0H0815)](https://www.gog.com/u/Florence_Heart). While she was enjoying the good life at her parents' place - complete with air conditioning and a huge swimming pool - she kept my spirits up by sending me photos of herself, her friends, her parents, and even her parents' dog. She reminded me that there's a wonderful world outside of a code editor every now and then... 🙈

  *Now that's what I call real support.* ❤️

Thank you both for having my back!

## 🤝 Support & Feedback

**GitHub Issues are intentionally disabled.** Health-related limitations prevent me from reliably managing separate issue trackers across all of my plugin repositories.

Before contacting me, follow [Troubleshooting](#-troubleshooting) and prepare a fresh Humble Bundle plugin log with a detailed description.

* **GOG:** Send me a message or add me as a friend through my [GOG profile](https://www.gog.com/u/melcom).
* **Email:** `melcom @ gmx.net`
* **Discord:** `.melcom` - the leading dot is part of the username. You can send me a message or add me as a friend.

Logs can be attached directly or shared using an accessible cloud storage link, such as Dropbox, OneDrive, Google Drive, or a similar service. Response times may vary depending on my health and available development time. Thank you for your understanding.
