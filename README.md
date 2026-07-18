# Humble Bundle Integration Plugin for GOG Galaxy 2.1+ (64-bit)

This repository contains the Humble Bundle integration plugin for the native 64-bit version of GOG Galaxy 2.1+. It is based on the original community integration and has been updated for the current GOG Galaxy client and Python 3.13. The project includes rebuilt 64-bit dependencies, initialization crash fixes, an updated .NET/pythonnet bridge, an interactive configurator, and ongoing maintenance.

---

## ✨ Features

* Imports your owned Humble Bundle games into GOG Galaxy
* Detects games installed through the Humble app
* Detects DRM-free games inside user-defined folders
* Installs, launches, and uninstalls supported games
* Tracks game time for games launched through the integration
* Includes an interactive configurator for initial setup and later changes
* Supports GOG Galaxy 2.1+ 64-bit and Python 3.13
* Includes rebuilt dependencies, compatibility fixes, and stability improvements

---

## 📦 Installation

### Automatic Installation with Plugin Updater (Recommended)

The easiest way to install the Humble Bundle integration is with the [melcom GOG Galaxy Plugin Updater](https://github.com/melcom-creations/galaxy-integrations-64bit/tree/main/tools/melcom-galaxy_plugin_updater). The updater detects existing integrations and can install any supported melcom plugins that are still missing.

1. Download and extract the Plugin Updater.
2. Double-click `update-plugins.bat`.
3. Select your preferred language.
4. Follow the displayed instructions.

### Manual Installation

1. Close GOG Galaxy completely and make sure it is no longer running in the system tray.
2. Download the latest release package from this repository.
3. Extract the ZIP archive directly into:

```text
%localappdata%\GOG.com\Galaxy\plugins\installed\
```

The resulting directory structure must look like this:

```text
%localappdata%\GOG.com\Galaxy\plugins\installed\
└── humble_f0ca3d80-a432-4d35-a9e3-60f27161ac3a\
    ├── manifest.json
    ├── plugin.py
    ├── configurator.bat
    ├── README.md
    └── ...
```

4. Continue with **Interactive Configurator** and **First Start and Initial Sync** below.

---

## 🔧 Interactive Configurator

The interactive configurator guides you through the setup, validates your input, and writes the required configuration automatically. It opens the first time you connect the Humble Bundle integration through GOG Galaxy. The old manual configuration workflow is no longer recommended.

The configurator lets you select the folders containing your DRM-free Humble games. It validates every path and warns you before creating a missing directory or accepting a potentially unsafe root location.

To change the configuration later, double-click the **Install** button of any Humble Bundle game in GOG Galaxy. If the configurator does not open that way, start it manually from:

```text
%localappdata%\GOG.com\Galaxy\plugins\installed\humble_f0ca3d80-a432-4d35-a9e3-60f27161ac3a\configurator.bat
```

### Configuration Steps

1. Select your preferred language.
2. Enter the folder containing your DRM-free Humble games.
3. Confirm folder creation if the directory does not exist.
4. Review and confirm the remaining settings.

Examples of valid game folders:

```text
D:\Humble
D:\Games\Humble
```

---

## 🚀 First Start and Initial Sync

For the first synchronization after installing, updating, or configuring the plugin:

1. If you use the Humble app, start it and keep it open.
2. Start GOG Galaxy.
3. Connect the Humble Bundle integration through **Settings -> Integrations** if necessary.
4. Complete the interactive configuration when it opens.
5. Open the account menu in the top-right corner and select **Sync integrations**.
6. Wait until the synchronization has finished.

---

## 🔄 Resetting the Plugin Database (Troubleshooting)

Reset the local plugin database only if the integration behaves unexpectedly or synchronization problems continue after restarting GOG Galaxy.

1. Close GOG Galaxy completely.
2. Open `C:\ProgramData\GOG.com\Galaxy\storage\plugins\`.
3. Find every file starting with `humble_` and ending in `-storage.db`.
4. Rename each matching file by appending `.old`, for example:

   `humble_xxxxxxxxx-storage.db` -> `humble_xxxxxxxxx-storage.db.old`

5. If you use the Humble app, start it and keep it open.
6. Start GOG Galaxy and reconnect the Humble Bundle integration if necessary.
7. Open the account menu in the top-right corner and select **Sync integrations**.
8. Wait until the synchronization has finished.

---

## ⚠️ Important

Do **not** place backup copies of this plugin inside the `plugins\installed` directory.

GOG Galaxy scans every folder inside this directory during startup. Duplicate plugin folders can lead to GUID conflicts or cause Galaxy to load an outdated version of the plugin.

---

## 🙏 Credits

**Original Plugin Author**  
Mesco

**Original Project**  
[UncleGoogle/galaxy-integration-humblebundle](https://github.com/UncleGoogle/galaxy-integration-humblebundle)

**64-bit Port, Python 3.13 Compatibility, Dependency Modernization and Configurator**  
melcom

---

## ❤️ Special Thanks

I want to take a moment to thank the people who kept me going during this intense development phase:

* A huge thank you to my friend [**Hustlefan**](https://www.gog.com/u/Hustlefan). Over the past few days, you've been much more than just moral support. You gave me the encouragement I needed, patiently put up with all my Discord spam, and helped beta test the plugins. I'm really happy that you're pleased with the results. Thanks so much for all your support, my friend.

* And a big thank you to my girlfriend [**Florence H.** (fl0H0815)](https://www.gog.com/u/Florence_Heart). While she was enjoying the good life at her parents' place - complete with air conditioning and a huge swimming pool - she kept my spirits up by sending me photos of herself, her friends, her parents, and even her parents' dog. She reminded me that there's a wonderful world outside of a code editor every now and then... 🙈

  *Now that's what I call real support.* ❤️

Thank you both for having my back!

---

## 🤝 Support & Feedback

This project is developed and maintained by one person. Response times may vary, especially during periods when health-related limitations reduce available development time.

**GitHub Issues are intentionally disabled.**

If you would like to report a bug or suggest an improvement, please use the contact form on my website:

📩 [Contact form](https://melcom-music.de/contact.html)

Thank you for your patience and support!
