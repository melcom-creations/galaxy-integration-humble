#Requires -Version 5.1

$scriptName = "melcom's Humble Bundle Plugin Configurator"
$scriptVersion = "Version 2"
$bannerSubtitle = "GOG Galaxy x Humble Bundle Integration Setup"
$Host.UI.RawUI.WindowTitle = "$scriptName - $scriptVersion"

# ============================================================
#   VALIDATION FUNCTIONS
# ============================================================

function Test-ValidGamePath {
    param([string]$Path)

    # Normalize user input first
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return @{ Valid = $false; Error = "PATH_EMPTY" }
    }

    $Path = $Path.Trim().Trim('"').Trim("'")

    # Reject drive-only input early
    if ($Path -match '^[A-Za-z]$') {
        return @{ Valid = $false; Error = "DRIVE_LETTER_ONLY" }
    }

    if ($Path -match '^[A-Za-z]:$') {
        return @{ Valid = $false; Error = "DRIVE_COLON_ONLY" }
    }

    # Reject pure drive root paths such as C:\, D:\ or E:\
    if ($Path -match '^[A-Za-z]:\\$') {
        return @{ Valid = $false; Error = "DRIVE_ROOT_ONLY" }
    }

    # Enforce an actual Windows path that starts with a drive and folder segment
    if ($Path -notmatch '^[A-Za-z]:\\') {
        return @{ Valid = $false; Error = "INVALID_PATH_FORMAT" }
    }

    # Split off the drive prefix and inspect the remaining segments
    $pathBody = $Path.Substring(3)

    # Trailing root-only variants like D:\. or D:\.. should still be rejected
    if ([string]::IsNullOrWhiteSpace($pathBody) -or $pathBody.TrimEnd('\').Length -eq 0) {
        return @{ Valid = $false; Error = "DRIVE_ROOT_ONLY" }
    }

    # Reject invalid characters inside the folder portion
    $invalidMatches = [regex]::Matches($pathBody, '[<>:"|?*]')
    if ($invalidMatches.Count -gt 0) {
        $badChars = (($invalidMatches | ForEach-Object { $_.Value }) | Select-Object -Unique) -join ''
        return @{ Valid = $false; Error = "INVALID_CHARS"; BadChars = $badChars }
    }

    # Resolve the input to a full path
    try {
        $fullPath = [System.IO.Path]::GetFullPath($Path)
    }
    catch {
        return @{ Valid = $false; Error = "INVALID_PATH_FORMAT"; Details = $_.Exception.Message }
    }

    # Reject paths that resolve back to the drive root
    try {
        $rootPath = [System.IO.Path]::GetPathRoot($fullPath)
        if (-not [string]::IsNullOrWhiteSpace($rootPath)) {
            $normalizedFull = $fullPath.TrimEnd('\')
            $normalizedRoot = $rootPath.TrimEnd('\')
            if ($normalizedFull -ieq $normalizedRoot) {
                return @{ Valid = $false; Error = "DRIVE_ROOT_ONLY"; Path = $fullPath }
            }
        }
    }
    catch {
        # Ignore root detection failures and continue with normal checks
    }

    # Check if path exists
    if (-not (Test-Path -LiteralPath $fullPath)) {
        return @{ Valid = $false; Error = "PATH_NOT_EXISTS"; Path = $fullPath }
    }

    # Check if it is a directory
    $item = Get-Item -LiteralPath $fullPath -ErrorAction SilentlyContinue
    if (-not $item -or $item.PSIsContainer -eq $false) {
        return @{ Valid = $false; Error = "NOT_A_DIRECTORY"; Path = $fullPath }
    }

    # Check if user has read permissions
    try {
        $null = Get-Acl -LiteralPath $fullPath
    }
    catch {
        return @{ Valid = $false; Error = "NO_READ_PERMISSION"; Path = $fullPath }
    }

    return @{ Valid = $true; Path = $fullPath }
}

function Test-CanCreateDirectory {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return @{ CanCreate = $false; Error = "PATH_EMPTY" }
    }

    $Path = $Path.Trim().Trim('"').Trim("'")

    if ($Path -match '^[A-Za-z]$') {
        return @{ CanCreate = $false; Error = "DRIVE_LETTER_ONLY" }
    }

    if ($Path -match '^[A-Za-z]:$' -or $Path -match '^[A-Za-z]:\\$') {
        return @{ CanCreate = $false; Error = "DRIVE_ROOT_ONLY" }
    }

    if ($Path -notmatch '^[A-Za-z]:\\') {
        return @{ CanCreate = $false; Error = "INVALID_PATH_FORMAT" }
    }

    $pathBody = $Path.Substring(3)
    if ([string]::IsNullOrWhiteSpace($pathBody) -or $pathBody.TrimEnd('\').Length -eq 0) {
        return @{ CanCreate = $false; Error = "DRIVE_ROOT_ONLY" }
    }

    $invalidMatches = [regex]::Matches($pathBody, '[<>:"|?*]')
    if ($invalidMatches.Count -gt 0) {
        return @{ CanCreate = $false; Error = "INVALID_CHARS" }
    }

    if ($Path.Length -gt 240) {
        return @{ CanCreate = $false; Error = "PATH_TOO_LONG"; Length = $Path.Length }
    }

    try {
        $fullPath = [System.IO.Path]::GetFullPath($Path)

        $rootPath = [System.IO.Path]::GetPathRoot($fullPath)
        if (-not [string]::IsNullOrWhiteSpace($rootPath)) {
            $normalizedFull = $fullPath.TrimEnd('\')
            $normalizedRoot = $rootPath.TrimEnd('\')
            if ($normalizedFull -ieq $normalizedRoot) {
                return @{ CanCreate = $false; Error = "DRIVE_ROOT_ONLY"; Path = $fullPath }
            }
        }

        $parentPath = Split-Path -Parent $fullPath

        if (-not (Test-Path -LiteralPath $parentPath)) {
            return @{ CanCreate = $false; Error = "PARENT_NOT_EXISTS"; Parent = $parentPath }
        }

        $testPath = New-Item -ItemType Directory -Path $fullPath -Force -ErrorAction Stop
        Remove-Item $testPath -Force -ErrorAction SilentlyContinue

        return @{ CanCreate = $true; Path = $fullPath }
    }
    catch {
        return @{ CanCreate = $false; Error = "CANNOT_CREATE"; Details = $_.Exception.Message }
    }
}

function Write-Banner {
    Clear-Host
    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host "          $scriptName" -ForegroundColor Cyan
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host "   $bannerSubtitle" -ForegroundColor DarkCyan
    Write-Host "   $scriptVersion" -ForegroundColor DarkGray
    Write-Host ""
}

function Write-Step {
    param([string]$Number, [string]$Title)
    $label = if ($lang -eq "DE") { "Schritt" } else { "Step" }
    Write-Host "  -- $label $Number : $Title --" -ForegroundColor DarkYellow
    Write-Host ""
}

function Write-Success {
    param([string]$Message)
    Write-Host "  [OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "  [!]  $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)

    $lines = @($Message -split "`r?`n")
    if ($lines.Count -eq 0) {
        Write-Host "  [X]  " -ForegroundColor Red
        return
    }

    Write-Host "  [X]  $($lines[0])" -ForegroundColor Red
    for ($i = 1; $i -lt $lines.Count; $i++) {
        if (-not [string]::IsNullOrWhiteSpace($lines[$i])) {
            Write-Host "       $($lines[$i])" -ForegroundColor Red
        }
        else {
            Write-Host ""
        }
    }
}

function Prompt-YesNo {
    param([string]$Question)
    $hint = if ($lang -eq "EN") { "[Y/N]" } else { "[J/N]" }
    while ($true) {
        Write-Host "  $Question $hint : " -NoNewline
        $input = (Read-Host).Trim().ToUpper()
        if ([string]::IsNullOrWhiteSpace($input)) {
            Write-Host ""
            Write-Err $str.YesNoInvalid
            Write-Host ""
            continue
        }
        if ($input -in $str.YesAnswers) { return $true }
        if ($input -eq $str.NoAnswer) { return $false }
        Write-Host ""
        Write-Err $str.YesNoInvalid
        Write-Host ""
    }
}

# ============================================================
#   LANGUAGE SELECTION
# ============================================================

function Show-LanguageSelection {
    while ($true) {
        Write-Banner
        Write-Host "  Select your language / Sprache auswaehlen:" -ForegroundColor White
        Write-Host ""
        Write-Host "    [1]  English" -ForegroundColor White
        Write-Host "    [2]  Deutsch" -ForegroundColor White
        Write-Host ""

        Write-Host "  Choice [1/2]: " -NoNewline
        $langChoice = (Read-Host).Trim()

        switch ($langChoice) {
            "1" { return "EN" }
            "2" { return "DE" }
            default {
                Write-Host ""
                Write-Err "Invalid choice. Please enter 1 or 2."
                Start-Sleep -Seconds 1
            }
        }
    }
}

$lang = Show-LanguageSelection

# ============================================================
#   STRINGS
# ============================================================

if ($lang -eq "EN") {
    $str = @{
        AppName              = "melcom's Humble Bundle Plugin Configurator"
        BannerSubtitle       = "GOG Galaxy x Humble Bundle Integration Setup"

        Step1Title           = "Game Directory"
        Step1Desc1           = "  Please enter the folder path where your Humble games are installed."
        Step1Desc2           = "  Example: D:\Games\Humble"
        Step1Prompt          = "Folder Path:"
        Step1Empty           = "No path entered. Please try again."
        Step1NotFound        = "The path does not exist on this PC: "
        Step1DriveLetterOnly = "You entered only a drive letter.`nPlease enter a real path like D:\Humble or D:\Spiele\Humble"
        Step1DriveRootOnly   = "That is only the drive root, not a Humble directory. Please enter a folder below it, for example D:\Humble or D:\Spiele\Humble"
        Step1NotADir         = "The path exists but is not a directory: "
        Step1NoPermission    = "No read permission for path: "
        Step1InvalidChars    = "Invalid characters in path: "
        Step1PathTooLong     = "The path is too long (max 240 characters): "
        Step1InvalidFormat   = "Invalid path format. Use a full Windows path like D:\Humble."
        Step1Create          = "Would you like to create this directory now?"
        Step1Created         = "Directory created successfully."
        Step1CreateFail      = "Could not create directory: "
        Step1CreateParentNotExists = "Parent directory does not exist: "
        Step1CreateInvalidChars = "Cannot create - invalid characters in path"
        Step1CreatePathTooLong = "Cannot create - path is too long"
        Step1RootWarning     = "That is only the drive root. This is not a Humble directory and can cause problems."
        Step1RootConfirm     = "Use this drive root anyway?"
        Step1TryAgain        = "Enter a different path?"
        Step1Found           = "Directory found."
        Step1Aborted         = "Setup cancelled."

        Step2Title           = "Game Sources"
        Step2Desc            = "  Which of your Humble Bundle games should appear in GOG Galaxy?"
        Step2Opt1            = "    [1]  Both  --  Steam Keys AND downloadable games"
        Step2Opt2            = "    [2]  Keys Only  --  Steam Keys only"
        Step2Opt3            = "    [3]  Downloads Only  --  downloadable games only"
        Step2Explain1        = @(
            "      When you buy a Humble Bundle, some games come as a Steam Key",
            "      (a code you redeem on Steam) and some are DRM-Free downloads",
            "      (you download and run them directly, no Steam needed).",
            "      ",
            "      [1] BOTH  -->  Show ALL your games. Steam Keys AND downloads.",
            "                     If you are not sure, pick this one.",
            "      ",
            "      [2] KEYS ONLY  -->  Only show Steam Keys.",
            "                     Pick this if you only care about Steam games.",
            "      ",
            "      [3] DOWNLOADS ONLY  -->  Only show DRM-Free downloads.",
            "                     Pick this if you only want non-Steam games."
        )
        Step2Prompt          = "Choice [1/2/3/B]:"
        Step2Invalid         = "Invalid choice. Please enter 1, 2, 3, or B."
        Step2Val1            = "Both (Keys & DRM-Free)"
        Step2Val2            = "Keys Only"
        Step2Val3            = "DRM-Free Only"

        Step3Title           = "Revealed Keys"
        Step3Desc1           = "  Should GOG Galaxy show Steam Keys you have already revealed?"
        Step3Opt1            = "    [Y]  Yes  --  show revealed keys"
        Step3Opt2            = "    [N]  No   --  hide revealed keys  (recommended)"
        Step3Explain         = @(
            "      When you go to humblebundle.com and click 'Reveal' on a game,",
            "      the key gets shown to you. After that it is called 'revealed'.",
            "      ",
            "      [Y] YES  -->  Show revealed keys in GOG Galaxy too.",
            "                    Pick this if you want to see ALL your keys,",
            "                    even the ones you already copied to Steam.",
            "      ",
            "      [N] NO   -->  Hide revealed keys. (Recommended)",
            "                    Pick this to keep things tidy. Games you already",
            "                    redeemed on Steam will show up there, not here."
        )
        Step3Prompt          = "Choice [Y/N/B]:"
        Step3Yes             = "Yes"
        Step3No              = "No"
        Step3Invalid         = "Invalid input. Please enter Y, N, or B."
        YesNoInvalid         = "Invalid input. Please enter Y or N."

        SummaryTitle         = "Summary"
        SummaryDir           = "   Game Directory     : "
        SummarySrc           = "   Library Sources    : "
        SummaryKeys          = "   Show Revealed Keys : "
        SummaryConfirm       = "Are these settings correct?"
        SummaryPrompt        = "Choice [Y/N/B]:"
        SummaryInvalid       = "Invalid input. Please enter Y, N, or B."

        CurrentPathLabel     = "  Current Path: "
        CurrentSelectionLabel = "  Current Selection: "
        BackLabel            = "    [B]  Back  --  return to the previous step"

        SavedTitle           = "Configuration saved:"
        VerifyFailed         = "Configuration verification failed."
        SaveFailed           = "Could not save configuration file: "
        DoneMsg              = @(
            "  GOG Galaxy picks up the new settings automatically.",
            "  Give it a moment -- the changes should be visible within",
            "  10 seconds.",
            "",
            "  If nothing happens in the next 10 seconds, restart GOG Galaxy.",
            "",
            "  If things still look wrong and you set a game folder:",
            "  Make sure your games are actually unpacked and ready to run.",
            "  Downloading a game and dropping a zip file into the folder is",
            "  NOT enough. The folder must contain the unpacked game files.",
            "",
            "  It should look like this:",
            "    D:\Games\Humble\YourGame\YourGame.exe",
            "    (the .exe may also be inside a subfolder -- that is fine)",
            "",
            "  What must NOT be in there:",
            "    D:\Games\Humble\YourGame\YourGame.zip",
            "    D:\Games\Humble\YourGame\YourGame.tar.gz",
            "",
            "  If you see a .zip or .tar.gz: unpack it first, then try again."
        )
        PressKey             = "  Press any key to exit..."
        YesAnswers           = @("Y", "J")
        NoAnswer             = "N"
    }
} else {
    $bannerSubtitle = "Einrichtung der GOG Galaxy x Humble Bundle Integration"
    $str = @{
        AppName              = "melcom's Humble Bundle Plugin Configurator"
        BannerSubtitle       = "Einrichtung der GOG Galaxy x Humble Bundle Integration"

        Step1Title           = "Spieleverzeichnis"
        Step1Desc1           = "  Gib den Pfad an, wo deine Humble-Spiele installiert sind."
        Step1Desc2           = "  Beispiel: D:\Games\Humble"
        Step1Prompt          = "Pfad:"
        Step1Empty           = "Kein Pfad eingegeben. Bitte versuche es erneut."
        Step1NotFound        = "Das Verzeichnis existiert nicht: "
        Step1DriveLetterOnly = "Du hast nur einen Laufwerksbuchstaben eingegeben.`nBitte gib einen wirklichen Pfad an, zum Beispiel D:\Humble oder D:\Spiele\Humble"
        Step1DriveRootOnly   = "Das ist nur das Laufwerk, nicht das Humble-Verzeichnis. Bitte gib einen Ordner darunter an, zum Beispiel D:\Humble oder D:\Spiele\Humble"
        Step1NotADir         = "Der Pfad existiert, ist aber kein Verzeichnis: "
        Step1NoPermission    = "Keine Leseberechtigung fuer Pfad: "
        Step1InvalidChars    = "Ungueltige Zeichen im Pfad: "
        Step1PathTooLong     = "Der Pfad ist zu lang (max. 240 Zeichen): "
        Step1InvalidFormat   = "Ungueltiges Pfadformat. Bitte einen vollstaendigen Windows-Pfad angeben, z.B. D:\Humble."
        Step1Create          = "Soll das Verzeichnis jetzt angelegt werden?"
        Step1Created         = "Verzeichnis erfolgreich angelegt."
        Step1CreateFail      = "Konnte nicht erstellt werden: "
        Step1CreateParentNotExists = "Elternverzeichnis existiert nicht: "
        Step1CreateInvalidChars = "Kann nicht erstellt werden - ungueltige Zeichen im Pfad"
        Step1CreatePathTooLong = "Kann nicht erstellt werden - Pfad ist zu lang"
        Step1RootWarning     = "Das ist nur das Laufwerk. Das ist kein Humble-Verzeichnis und kann Probleme verursachen."
        Step1RootConfirm     = "Dieses Laufwerk trotzdem verwenden?"
        Step1TryAgain        = "Anderen Pfad eingeben?"
        Step1Found           = "Verzeichnis gefunden."
        Step1Aborted         = "Konfiguration abgebrochen."

        Step2Title           = "Spielquellen"
        Step2Desc            = "  Welche Spiele aus deinem Humble Bundle sollen in GOG Galaxy erscheinen?"
        Step2Opt1            = "    [1]  Beides  --  Steam-Keys UND herunterladbare Spiele"
        Step2Opt2            = "    [2]  Nur Keys  --  nur Steam-Keys"
        Step2Opt3            = "    [3]  Nur Downloads  --  nur herunterladbare Spiele"
        Step2Explain1        = @(
            "      Wenn du ein Humble Bundle kaufst, gibt es zwei Arten von Spielen:",
            "      Manche kommen als Steam-Key (ein Code, den du bei Steam einloest),",
            "      andere sind DRM-Free-Downloads (du laedt sie direkt runter,",
            "      kein Steam noetig).",
            "      ",
            "      [1] BEIDES  -->  Zeige ALLE deine Spiele. Keys UND Downloads.",
            "                       Wenn du nicht sicher bist, nimm diese Option.",
            "      ",
            "      [2] NUR KEYS  -->  Zeige nur Steam-Keys.",
            "                       Waehle das, wenn du nur Steam-Spiele willst.",
            "      ",
            "      [3] NUR DOWNLOADS  -->  Zeige nur DRM-Free-Downloads.",
            "                       Waehle das, wenn du nur Nicht-Steam-Spiele willst."
        )
        Step2Prompt          = "Auswahl [1/2/3/B]:"
        Step2Invalid         = "Ungueltige Auswahl. Bitte 1, 2, 3 oder B eingeben."
        Step2Val1            = "Beides (Keys & DRM-Free)"
        Step2Val2            = "Nur Keys"
        Step2Val3            = "Nur DRM-Free"

        Step3Title           = "Aufgedeckte Keys"
        Step3Desc1           = "  Sollen bereits aufgedeckte Steam-Keys in GOG Galaxy angezeigt werden?"
        Step3Opt1            = "    [J]  Ja    --  aufgedeckte Keys anzeigen"
        Step3Opt2            = "    [N]  Nein  --  aufgedeckte Keys ausblenden  (empfohlen)"
        Step3Explain         = @(
            "      Wenn du auf humblebundle.com bei einem Spiel auf 'Aufdecken'",
            "      geklickt hast, wurde dir der Key angezeigt. Dieser Key gilt",
            "      dann als 'aufgedeckt'.",
            "      ",
            "      [J] JA   -->  Aufgedeckte Keys trotzdem in GOG Galaxy zeigen.",
            "                    Waehle das, wenn du ALLE Keys sehen willst,",
            "                    auch die, die du schon bei Steam eingeloest hast.",
            "      ",
            "      [N] NEIN -->  Aufgedeckte Keys ausblenden. (Empfohlen)",
            "                    Waehle das fuer Uebersichtlichkeit. Spiele die du",
            "                    schon bei Steam eingeloest hast, tauchen dort auf."
        )
        Step3Prompt          = "Aufgedeckte Keys anzeigen [J/N/B]:"
        Step3Yes             = "Ja"
        Step3No              = "Nein"
        Step3Invalid         = "Ungueltige Eingabe. Bitte J, N oder B eingeben."
        YesNoInvalid         = "Ungueltige Eingabe. Bitte J oder N eingeben."

        SummaryTitle         = "Zusammenfassung"
        SummaryDir           = "   Spieleverzeichnis  : "
        SummarySrc           = "   Bibliotheksquellen : "
        SummaryKeys          = "   Aufgedeckte Keys   : "
        SummaryConfirm       = "Sind diese Einstellungen korrekt?"
        SummaryPrompt        = "Auswahl [J/N/B]:"
        SummaryInvalid       = "Ungueltige Eingabe. Bitte J, N oder B eingeben."

        CurrentPathLabel     = "  Aktueller Pfad: "
        CurrentSelectionLabel = "  Aktuelle Auswahl: "
        BackLabel            = "    [B]  Zurueck  --  zur vorherigen Seite"

        SavedTitle           = "Konfiguration gespeichert:"
        VerifyFailed         = "Konfigurationspruefung fehlgeschlagen."
        SaveFailed           = "Konfigurationsdatei konnte nicht gespeichert werden: "
        DoneMsg              = @(
            "  GOG Galaxy uebernimmt die neuen Einstellungen automatisch.",
            "  Warte einen Augenblick -- die Aenderungen sollten innerhalb von",
            "  10 Sekunden sichtbar werden.",
            "",
            "  Tut sich in den naechsten 10 Sekunden nichts, starte GOG neu.",
            "",
            "  Wenn danach immer noch nichts passiert und du einen Spieleordner",
            "  angegeben hast: Pruefe, ob deine Spiele wirklich entpackt vorliegen.",
            "  Es reicht nicht, eine ZIP-Datei in den Ordner zu legen.",
            "  Die Spieldateien muessen vollstaendig entpackt sein.",
            "",
            "  So sollte es aussehen:",
            "    D:\Games\Humble\DeinSpiel\DeinSpiel.exe",
            "    (die .exe darf sich auch in einem Unterordner befinden -- kein Problem)",
            "",
            "  Was NICHT drin sein darf:",
            "    D:\Games\Humble\DeinSpiel\DeinSpiel.zip",
            "    D:\Games\Humble\DeinSpiel\DeinSpiel.tar.gz",
            "",
            "  Siehst du eine .zip oder .tar.gz: erst entpacken, dann nochmal probieren."
        )
        PressKey             = "  Druecke eine Taste zum Beenden..."
        YesAnswers           = @("J", "Y")
        NoAnswer             = "N"
    }
}

# ============================================================
#   STEP NAVIGATION
# ============================================================

$currentStep = 1

while ($true) {
    switch ($currentStep) {
        1 {
            while ($true) {
                $advanceToNextStep = $false
                Write-Banner
                Write-Step "1" $str.Step1Title
                Write-Host $str.Step1Desc1 -ForegroundColor Gray
                Write-Host $str.Step1Desc2 -ForegroundColor DarkGray
                Write-Host ""
                if ($null -ne $userPath) {
                    Write-Host ($str.CurrentPathLabel + $userPath) -ForegroundColor DarkGray
                    Write-Host ""
                }

                Write-Host "  $($str.Step1Prompt) " -NoNewline
                $enteredPath = (Read-Host).Trim().Trim('"').Trim("'")

                # Empty input handling
                if ([string]::IsNullOrWhiteSpace($enteredPath)) {
                    if (-not [string]::IsNullOrWhiteSpace($userPath)) {
                        $currentStep = 2
                        break
                    }

                    Write-Host ""
                    Write-Err $str.Step1Empty
                    Start-Sleep -Seconds 2
                    continue
                }

                # Reject drive letter only input immediately
                if ($enteredPath -match '^[A-Za-z]$' -or $enteredPath -match '^[A-Za-z]:$') {
                    Write-Host ""
                    Write-Err $str.Step1DriveLetterOnly
                    Start-Sleep -Seconds 2
                    continue
                }

                # Drive root is a special high-risk case: warn and ask for confirmation
                if ($enteredPath -match '^[A-Za-z]:\\$') {
                    Write-Host ""
                    Write-Warn $str.Step1RootWarning
                    Write-Host ""
                    if (Prompt-YesNo $str.Step1RootConfirm) {
                        try {
                            $userPath = [System.IO.Path]::GetFullPath($enteredPath)
                        }
                        catch {
                            $userPath = $enteredPath
                        }

                        Write-Host ""
                        Write-Success $str.Step1Found
                        Start-Sleep -Milliseconds 600
                        $currentStep = 2
                        $advanceToNextStep = $true
                        break
                    }

                    Write-Host ""
                    Start-Sleep -Seconds 2
                    continue
                }

                # Validate path with strict directory rules
                $validation = Test-ValidGamePath $enteredPath

                if ($validation.Valid) {
                    $userPath = $validation.Path
                    Write-Host ""
                    Write-Success $str.Step1Found
                    Start-Sleep -Milliseconds 600
                    $currentStep = 2
                    $advanceToNextStep = $true
                    break
                }

                # Handle validation errors and create prompts
                Write-Host ""

                switch ($validation.Error) {
                    "PATH_EMPTY" {
                        Write-Err $str.Step1Empty
                    }
                    "DRIVE_LETTER_ONLY" {
                        Write-Err $str.Step1DriveLetterOnly
                    }
                    "DRIVE_COLON_ONLY" {
                        Write-Err $str.Step1DriveLetterOnly
                    }
                    "DRIVE_ROOT_ONLY" {
                        Write-Warn $str.Step1RootWarning
                    }
                    "INVALID_CHARS" {
                        Write-Err ($str.Step1InvalidChars + $validation.BadChars)
                    }
                    "PATH_TOO_LONG" {
                        Write-Err ($str.Step1PathTooLong + $validation.Length + " chars")
                    }
                    "INVALID_PATH_FORMAT" {
                        if ($validation.Details) {
                            Write-Err ($str.Step1InvalidFormat + " " + $validation.Details)
                        }
                        else {
                            Write-Err $str.Step1InvalidFormat
                        }
                    }
                    "PATH_NOT_EXISTS" {
                        $canCreate = Test-CanCreateDirectory $enteredPath

                        if ($canCreate.CanCreate) {
                            Write-Warn ($str.Step1NotFound + $validation.Path)
                            Write-Host ""
                            if (Prompt-YesNo $str.Step1Create) {
                                try {
                                    $created = New-Item -ItemType Directory -Path $validation.Path -Force -ErrorAction Stop
                                    $userPath = $created.FullName
                                    Write-Host ""
                                    Write-Success $str.Step1Created
                                    Start-Sleep -Milliseconds 600
                                    $currentStep = 2
                                    $advanceToNextStep = $true
                                    break
                                }
                                catch {
                                    Write-Err ($str.Step1CreateFail + $_.Exception.Message)
                                }
                            }
                        }
                        else {
                            switch ($canCreate.Error) {
                                "PARENT_NOT_EXISTS" {
                                    Write-Err ($str.Step1CreateParentNotExists + $canCreate.Parent)
                                }
                                "INVALID_CHARS" {
                                    Write-Err $str.Step1CreateInvalidChars
                                }
                                "PATH_TOO_LONG" {
                                    Write-Err $str.Step1CreatePathTooLong
                                }
                                "DRIVE_ROOT_ONLY" {
                                    Write-Warn $str.Step1RootWarning
                                }
                                "CANNOT_CREATE" {
                                    if ($canCreate.Details) {
                                        Write-Err ($str.Step1CreateFail + $canCreate.Details)
                                    }
                                    else {
                                        Write-Err $str.Step1CreateFail
                                    }
                                }
                                default {
                                    Write-Err ($str.Step1NotFound + $validation.Path)
                                }
                            }
                        }
                    }
                    "NOT_A_DIRECTORY" {
                        Write-Err ($str.Step1NotADir + $validation.Path)
                    }
                    "NO_READ_PERMISSION" {
                        Write-Err ($str.Step1NoPermission + $validation.Path)
                    }
                    default {
                        Write-Err ($str.Step1NotFound + $enteredPath)
                    }
                }

                if ($advanceToNextStep) {
                    break
                }

                Write-Host ""
                Start-Sleep -Seconds 2
            }
        }

        2 {
            while ($true) {
                Write-Banner
                Write-Step "2" $str.Step2Title
                Write-Host $str.Step2Desc -ForegroundColor Gray
                Write-Host ""
                if ($null -ne $sourcesTxt) {
                    Write-Host ($str.CurrentSelectionLabel + $sourcesTxt) -ForegroundColor DarkGray
                    Write-Host ""
                }
                Write-Host $str.Step2Opt1 -ForegroundColor White
                Write-Host $str.Step2Opt2 -ForegroundColor White
                Write-Host $str.Step2Opt3 -ForegroundColor White
                Write-Host $str.BackLabel -ForegroundColor DarkGray
                Write-Host ""
                foreach ($line in $str.Step2Explain1) {
                    Write-Host $line -ForegroundColor DarkGray
                }
                Write-Host ""

                Write-Host "  $($str.Step2Prompt) " -NoNewline
                $sourceChoice = (Read-Host).Trim()

                if ([string]::IsNullOrWhiteSpace($sourceChoice)) {
                    if ($null -ne $sourcesVal) {
                        $currentStep = 3
                        break
                    }

                    Write-Host ""
                    Write-Err $str.Step2Invalid
                    Start-Sleep -Seconds 2
                    continue
                }

                switch ($sourceChoice.ToUpper()) {
                    "1" { $sourcesVal = '[ "keys", "drm-free" ]'; $sourcesTxt = $str.Step2Val1; $currentStep = 3 }
                    "2" { $sourcesVal = '[ "keys" ]'; $sourcesTxt = $str.Step2Val2; $currentStep = 3 }
                    "3" { $sourcesVal = '[ "drm-free" ]'; $sourcesTxt = $str.Step2Val3; $currentStep = 3 }
                    "B" { $currentStep = 1 }
                    default {
                        Write-Host ""
                        Write-Err $str.Step2Invalid
                        Start-Sleep -Seconds 1
                    }
                }

                if ($currentStep -eq 1 -or $currentStep -eq 3) {
                    break
                }
            }
        }

        3 {
            while ($true) {
                Write-Banner
                Write-Step "3" $str.Step3Title
                Write-Host $str.Step3Desc1 -ForegroundColor Gray
                Write-Host ""
                if ($null -ne $showKeysTxt) {
                    Write-Host ($str.CurrentSelectionLabel + $showKeysTxt) -ForegroundColor DarkGray
                    Write-Host ""
                }
                Write-Host $str.Step3Opt1 -ForegroundColor White
                Write-Host $str.Step3Opt2 -ForegroundColor White
                Write-Host $str.BackLabel -ForegroundColor DarkGray
                Write-Host ""
                foreach ($line in $str.Step3Explain) {
                    Write-Host $line -ForegroundColor DarkGray
                }
                Write-Host ""

                Write-Host "  $($str.Step3Prompt) " -NoNewline
                $showRevealedInput = (Read-Host).Trim().ToUpper()

                if ([string]::IsNullOrWhiteSpace($showRevealedInput)) {
                    if ($null -ne $showRevealedKeys) {
                        $currentStep = 4
                        break
                    }

                    Write-Host ""
                    Write-Err $str.Step3Invalid
                    Start-Sleep -Seconds 2
                    continue
                }

                if ($showRevealedInput -eq "B") {
                    $currentStep = 2
                    break
                }

                switch ($showRevealedInput) {
                    { $_ -in $str.YesAnswers } {
                        $showRevealedKeys = $true
                        $showKeysVal = "true"
                        $showKeysTxt = $str.Step3Yes
                        $currentStep = 4
                        break
                    }
                    { $_ -eq $str.NoAnswer } {
                        $showRevealedKeys = $false
                        $showKeysVal = "false"
                        $showKeysTxt = $str.Step3No
                        $currentStep = 4
                        break
                    }
                    default {
                        Write-Host ""
                        Write-Err $str.Step3Invalid
                        Start-Sleep -Seconds 1
                    }
                }

                if ($currentStep -eq 2 -or $currentStep -eq 4) {
                    break
                }
            }
        }

        4 {
            $confirmed = $false
            while (-not $confirmed) {
                Write-Banner
                Write-Host "  -- $($str.SummaryTitle) --" -ForegroundColor DarkYellow
                Write-Host ""
                Write-Host $str.SummaryDir -ForegroundColor DarkGray -NoNewline
                Write-Host $userPath -ForegroundColor White
                Write-Host $str.SummarySrc -ForegroundColor DarkGray -NoNewline
                Write-Host $sourcesTxt -ForegroundColor White
                Write-Host $str.SummaryKeys -ForegroundColor DarkGray -NoNewline
                Write-Host $showKeysTxt -ForegroundColor White
                Write-Host ""
                Write-Host "  ============================================================" -ForegroundColor DarkCyan
                Write-Host ""
                Write-Host $str.BackLabel -ForegroundColor DarkGray
                Write-Host ""

                Write-Host "  $($str.SummaryConfirm) $($str.SummaryPrompt) " -NoNewline
                $summaryChoice = (Read-Host).Trim().ToUpper()

                if ($summaryChoice -eq "B") {
                    $currentStep = 3
                    break
                }

                if ($summaryChoice -in $str.YesAnswers) {
                    $confirmed = $true
                    break
                }

                if ($summaryChoice -eq $str.NoAnswer) {
                    $currentStep = 3
                    break
                }

                Write-Host ""
                Write-Err $str.SummaryInvalid
                Start-Sleep -Seconds 1
            }

            if ($confirmed) {
                $currentStep = 5
                break
            }
        }

        5 { break }
    }

    if ($currentStep -eq 5) {
        break
    }
}

# ============================================================
#   SAVE CONFIG
# ============================================================

$escapedPath = $userPath -replace '\\', '\\\\'
$configDir = "$env:LOCALAPPDATA\galaxy-hb"
$configFile = "$configDir\galaxy-humble-config.ini"

# Create config directory
try {
    if (-not (Test-Path $configDir)) {
        New-Item -ItemType Directory -Path $configDir -Force -ErrorAction Stop | Out-Null
    }
}
catch {
    Write-Banner
    Write-Err ($str.SaveFailed + $_.Exception.Message)
    Write-Host ""
    Write-Host $configDir -ForegroundColor DarkGray
    Write-Host ""
    Write-Host $str.PressKey -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# Write config file
$crlf = "`r`n"
$config = "[library]$crlf" +
          "sources = $sourcesVal$crlf" +
          "show_revealed_keys = $showKeysVal$crlf" +
          "$crlf" +
          "[installed]$crlf" +
          "search_dirs = [ `"$escapedPath`" ]$crlf"

try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($config)
    [System.IO.File]::WriteAllBytes($configFile, $bytes)
}
catch {
    Write-Banner
    Write-Err ($str.SaveFailed + $_.Exception.Message)
    Write-Host ""
    Write-Host $configFile -ForegroundColor DarkGray
    Write-Host ""
    Write-Host $str.PressKey -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# ============================================================
#   VERIFY CONFIG
# ============================================================

try {
    $verifyContent = [System.IO.File]::ReadAllText($configFile, [System.Text.Encoding]::UTF8)

    if ($verifyContent -ne $config) {
        Write-Banner
        Write-Err $str.VerifyFailed
        Write-Host ""
        Write-Host "Expected:" -ForegroundColor Yellow
        Write-Host $config -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "Got:" -ForegroundColor Yellow
        Write-Host $verifyContent -ForegroundColor DarkGray
        Write-Host ""
        Write-Host $str.PressKey -ForegroundColor DarkGray
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        exit 1
    }
}
catch {
    Write-Banner
    Write-Err $str.VerifyFailed
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor DarkGray
    Write-Host ""
    Write-Host $str.PressKey -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# ============================================================
#   DONE
# ============================================================

Write-Banner
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""
Write-Success $str.SavedTitle
Write-Host "           $configFile" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor DarkCyan
Write-Host ""
for ($i = 0; $i -lt $str.DoneMsg.Count; $i++) {
    $line = $str.DoneMsg[$i]
    if ([string]::IsNullOrWhiteSpace($line)) {
        Write-Host ""
        continue
    }

    if ($i -eq 0) {
        Write-Host $line -ForegroundColor Green
    }
    elseif ($i -in 1, 2) {
        Write-Host $line -ForegroundColor Red
    }
    else {
        Write-Host $line -ForegroundColor Yellow
    }
}
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor DarkCyan
Write-Host ""
Write-Host $str.PressKey -ForegroundColor DarkGray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")