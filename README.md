# Humble Bundle Plugin for GOG Galaxy 2.1+ (64-bit)

This repository contains the Humble Bundle integration plugin for the 64-bit version of GOG Galaxy 2.1+.

The original community integration has been updated for the current 64-bit GOG Galaxy client and Python 3.13. This release includes rebuilt 64-bit dependencies, crash fixes during initialization, an updated .NET/pythonnet bridge, and an interactive configurator for first-time setup and later changes.

---

## ✨ Features

* Compatible with GOG Galaxy 2.1+ (64-bit)
* Python 3.13 support
* Updated 64-bit dependencies
* Improved stability and compatibility
* Interactive configurator for setup and later changes
* Ongoing maintenance and bug fixes

---

## 📦 Installation

### Standard Installation (Recommended)

1. Close GOG Galaxy completely.
2. Download the latest release ZIP from this repository.
3. Open the following folder:

```text
%localappdata%\GOG.com\Galaxy\plugins\installed\
```

1. Extract the ZIP archive **directly into this folder**.

The resulting directory structure **must** look like this:

```text
%localappdata%\GOG.com\Galaxy\plugins\installed\
└── humble_f0ca3d80-a432-4d35-a9e3-60f27161ac3a\
    ├── manifest.json
    ├── plugin.py
    ├── README.md
    └── ...
```

1. Start GOG Galaxy.

---

## 🔧 Interactive Configurator

The old manual config-file workflow is no longer the recommended way to configure the plugin.

The new interactive configurator guides you through setup step by step, validates your input, and writes the correct configuration for you. It starts automatically the first time you connect to Humble Bundle through the 64-bit GOG Galaxy client v2.1+.

If you want to change the settings later, simply double-click the left mouse button on the **Install** button of any Humble Bundle game and the configurator opens again.

If that still does not work, open this folder manually:

```text
%localappdata%\GOG.com\Galaxy\plugins\installed\humble_f0ca3d80-a432-4d35-a9e3-60f27161ac3a\
```

Then start:

```text
configurator.bat
```

The configurator helps you define the folder where your DRM-free Humble games are installed. It uses strict path validation, clear error messages, and safe prompts when a folder does not exist yet or when a root path could be risky.

Typical flow:

1. Start the configurator.
2. Choose your language.
3. Enter the game folder path.
4. Confirm folder creation if the directory does not exist.
5. Continue with the remaining setup steps.

Examples of valid paths include:

```text
D:\Humble
D:\Games\Humble
```

---

## 🔄 Resetting the Plugin Database (Recommended)

If the plugin behaves unexpectedly after an update, resetting the local plugin database is recommended.

1. Open `C:\ProgramData\GOG.com\Galaxy\storage\plugins\` and find the files starting with `humble_` and ending in `-storage.db`.
2. Rename each by appending `.old` (e.g. `humble_xxxxxxxxx-storage.db` -> `humble_xxxxxxxxx-storage.db.old`).
3. Start GOG Galaxy again and reconnect the Humble Bundle integration if necessary.

### 🚀 First Start and Initial Sync (Important)

For a clean first run after installing or updating the plugin:

1. Close GOG Galaxy.
2. Open this folder:

```text
C:\ProgramData\GOG.com\Galaxy\storage\plugins\
```

1. If a `humble_...-storage.db` file exists there, delete it.
2. Start GOG Galaxy.
3. If you use the Humble app locally, keep it open during the first sync.
4. In GOG Galaxy, open the account menu (top-right) and click **Sync integrations**.
5. Wait until sync finishes.

---

## ⚠️ Important

Do **not** place backup copies of this plugin inside the `plugins\installed` directory.

GOG Galaxy scans every folder inside this directory during startup. Duplicate plugin folders can lead to GUID conflicts or cause Galaxy to load an outdated version of the plugin.

---

## 🙏 Credits

**Original Plugin Author**  
Mesco

**Original Project**  
[github.com/UncleGoogle/galaxy-integration-humblebundle](https://github.com/UncleGoogle/galaxy-integration-humblebundle/)

**64-bit Port, Python 3.13 Compatibility Fixes, Dependency Modernization, Configurator Work**  
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
